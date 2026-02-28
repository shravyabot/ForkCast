"""ForkCast — Autonomous Meal Planner, Calorie Tracker & Health Dashboard."""
import sys, os, json, zipfile, io, xml.etree.ElementTree as ET
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from agents.orchestrator import Orchestrator, PipelineState
from agents.calorie_tracker import CalorieTracker, calculate_targets, GOAL_PRESETS
from openai import OpenAI
import config

st.set_page_config(page_title="ForkCast 🍴", page_icon="🍴", layout="wide", initial_sidebar_state="expanded")

# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.main-header { font-size: 2.5rem; font-weight: 700;
    background: linear-gradient(90deg, #ff6b35, #f7931e, #ffcc02);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0; }
.sub-header { font-size: 1.1rem; color: #888; margin-top: -10px; margin-bottom: 20px; }
.meal-card { background: #1e1e2e; border-radius: 12px; padding: 16px; margin: 8px 0; border-left: 4px solid #ff6b35; }
.meal-card h4 { margin: 0 0 4px 0; color: #ff6b35; } .meal-card p { margin: 0; color: #ccc; }
.log-entry { font-family: monospace; font-size: 0.85rem; padding: 4px 0; border-bottom: 1px solid #333; }
.order-card { background: #1a3a1a; border-radius: 12px; padding: 20px; border: 2px solid #4caf50; margin: 16px 0; }
.badge { display: inline-block; padding: 6px 14px; border-radius: 20px; margin: 4px; font-size: 0.85rem; font-weight: 600; }
.badge-earned { background: #ffcc0230; color: #ffcc02; border: 1px solid #ffcc02; }
.badge-locked { background: #33333350; color: #666; border: 1px solid #444; }
.health-score-big { font-size: 3rem; font-weight: 700; text-align: center; }
.profile-card { background: #1e1e2e; border-radius: 16px; padding: 24px; text-align: center; border: 1px solid #333; }
.stat-card { background: #1e1e2e; border-radius: 12px; padding: 16px; text-align: center; }
.stat-card h2 { margin: 0; color: #ff6b35; } .stat-card p { margin: 4px 0 0; color: #888; font-size: 0.85rem; }
/* Floating chatbot */
.chat-toggle { position: fixed; bottom: 24px; right: 24px; z-index: 9999;
    background: linear-gradient(135deg, #ff6b35, #f7931e); color: white;
    border: none; border-radius: 50%; width: 60px; height: 60px;
    font-size: 1.5rem; cursor: pointer; box-shadow: 0 4px 20px rgba(255,107,53,0.4); }
</style>
""", unsafe_allow_html=True)

# ── Profiles (persistent) ──────────────────────────────────────────
PROFILES_PATH = os.path.join(os.path.dirname(__file__), "profiles.json")

def _load_profiles():
    if os.path.exists(PROFILES_PATH):
        with open(PROFILES_PATH, "r") as f:
            return json.load(f)
    return {}

def _save_profiles(profiles):
    with open(PROFILES_PATH, "w") as f:
        json.dump(profiles, f, indent=2, ensure_ascii=False)

# ── Session State ──────────────────────────────────────────────────
defaults = {
    "state": None, "tracked_meals": [], "water_glasses": 0, "streak_days": 1,
    "badges": [], "workouts": [], "calorie_tracker": CalorieTracker(),
    "existing_ingredients": "", "chat_messages": [], "chat_open": False,
    "profile": {"name": "", "avatar": "🧑‍🍳"},
    "apple_health": None, "active_profile": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

saved_profiles = _load_profiles()

# ── Header ─────────────────────────────────────────────────────────
st.markdown('<p class="main-header">🍴 ForkCast</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">From fridge to fork, fully autonomous — Powered by Tavily, Neo4j, OpenAI, Airbyte & Render</p>', unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    # Profile section
    st.header("👤 Profile")
    profile_names = ["— New Profile —"] + list(saved_profiles.keys())
    selected_profile = st.selectbox("Switch profile", profile_names,
        index=profile_names.index(st.session_state.active_profile) if st.session_state.active_profile in profile_names else 0,
        key="profile_selector")

    # Load selected profile
    if selected_profile != "— New Profile —" and selected_profile in saved_profiles:
        p = saved_profiles[selected_profile]
        if st.session_state.active_profile != selected_profile:
            st.session_state.active_profile = selected_profile
            st.session_state.profile = {"name": p["name"], "avatar": p.get("avatar", "🧑‍🍳")}
            st.rerun()
    else:
        if st.session_state.active_profile is not None and selected_profile == "— New Profile —":
            st.session_state.active_profile = None
            st.session_state.profile = {"name": "", "avatar": "🧑‍🍳"}
            st.rerun()

    # If a saved profile is active, pull its defaults
    _p = saved_profiles.get(st.session_state.active_profile, {})

    avatar_options = ["🧑‍🍳", "👨‍🍳", "👩‍🍳", "🏃", "🧘", "💪", "🏋️", "🚴"]
    col_av, col_name = st.columns([1, 3])
    with col_av:
        st.session_state.profile["avatar"] = st.selectbox("Avatar", avatar_options,
            index=avatar_options.index(st.session_state.profile.get("avatar", "🧑‍🍳")), label_visibility="collapsed")
    with col_name:
        st.session_state.profile["name"] = st.text_input("Name",
            value=st.session_state.profile["name"], placeholder="Your name", label_visibility="collapsed")

    st.divider()
    st.header("⚙️ Preferences")
    dietary_preferences = st.text_input("🥗 Dietary", value="healthy, high-protein")
    cuisine_preferences = st.text_input("🌍 Cuisine", value="Mediterranean, Asian")
    household_size = st.slider("👨‍👩‍👧‍👦 Household", 1, 8, 2)
    budget = st.slider("💰 Budget ($/week)", 50, 500, 150, step=10)
    location = st.text_input("📍 Location", value="San Francisco, CA")

    st.divider()
    st.header("🧊 My Pantry")
    st.session_state.existing_ingredients = st.text_area("Ingredients at home",
        value=st.session_state.existing_ingredients,
        placeholder="olive oil, garlic, rice, eggs", height=60, label_visibility="collapsed")

    st.divider()
    st.header("🎯 Goals")
    goal_options = ["weight_loss", "maintenance", "muscle_gain"]
    goal = st.selectbox("Goal", goal_options,
        format_func=lambda x: GOAL_PRESETS[x]["label"],
        index=goal_options.index(_p.get("goal", "maintenance")))
    cg1, cg2 = st.columns(2)
    with cg1:
        weight_kg = st.number_input("Weight (kg)", 40.0, 200.0, _p.get("weight_kg", 70.0), 0.5)
        age = st.number_input("Age", 15, 100, _p.get("age", 28))
    with cg2:
        height_cm = st.number_input("Height (cm)", 120.0, 250.0, _p.get("height_cm", 170.0), 0.5)
        gender_options = ["Male", "Female"]
        gender = st.selectbox("Gender", gender_options,
            index=gender_options.index(_p.get("gender", "Male")))
    activity_options = ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Extremely Active"]
    activity_level = st.selectbox("Activity", activity_options,
        index=activity_options.index(_p.get("activity", "Moderately Active")))
    targets = calculate_targets(weight_kg, height_cm, age, gender, goal, activity_level)

    # Save / Delete profile buttons
    st.divider()
    sv1, sv2 = st.columns(2)
    with sv1:
        if st.button("💾 Save Profile", use_container_width=True):
            pname = st.session_state.profile["name"].strip()
            if pname:
                saved_profiles[pname] = {
                    "name": pname, "avatar": st.session_state.profile["avatar"],
                    "age": age, "height_cm": height_cm, "weight_kg": weight_kg,
                    "gender": gender, "activity": activity_level, "goal": goal,
                }
                _save_profiles(saved_profiles)
                st.session_state.active_profile = pname
                st.toast(f"✅ Saved profile: {pname}")
                st.rerun()
            else:
                st.warning("Enter a name first.")
    with sv2:
        if st.session_state.active_profile and st.button("🗑️ Delete", use_container_width=True):
            saved_profiles.pop(st.session_state.active_profile, None)
            _save_profiles(saved_profiles)
            st.session_state.active_profile = None
            st.session_state.profile = {"name": "", "avatar": "🧑‍🍳"}
            st.toast("Profile deleted.")
            st.rerun()

    st.divider()
    run_button = st.button("🚀 Start Autonomous Planning", type="primary", use_container_width=True)
    st.divider()
    st.caption("**Sponsors:** 🔍 Tavily • 🕸️ Neo4j • 🤖 OpenAI • 🔄 Airbyte • ☁️ Render")

existing_list = [x.strip().lower() for x in st.session_state.existing_ingredients.split(",") if x.strip()]

# ── Apple Health Parser ────────────────────────────────────────────
from collections import defaultdict

def _extract_xml_bytes(source):
    """Accept raw XML/ZIP bytes or a file path and return XML bytes."""
    if isinstance(source, str):  # file path
        if source.endswith(".zip"):
            with zipfile.ZipFile(source) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml") and "export" in name.lower():
                        return zf.read(name)
        else:
            with open(source, "rb") as f:
                return f.read()
    else:  # bytes
        try:
            with zipfile.ZipFile(io.BytesIO(source)) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml"):
                        return zf.read(name)
        except zipfile.BadZipFile:
            pass
        return source
    return source

@st.cache_data(show_spinner=False)
def parse_apple_health(source):
    """Parse Apple Health export into daily breakdowns."""
    data = {
        "imported": True, "steps_by_day": {}, "calories_by_day": {},
        "distance_by_day": {}, "flights_by_day": {}, "weight_entries": [], "workouts": [],
    }
    try:
        xml_bytes = _extract_xml_bytes(source)
        root = ET.fromstring(xml_bytes)
        steps_dd, cal_dd, dist_dd, flights_dd = defaultdict(int), defaultdict(int), defaultdict(float), defaultdict(int)
        for record in root.iter("Record"):
            rtype = record.get("type", "")
            value = record.get("value", "0")
            date = record.get("startDate", "")[:10]
            if rtype == "HKQuantityTypeIdentifierStepCount":
                steps_dd[date] += int(float(value))
            elif rtype == "HKQuantityTypeIdentifierActiveEnergyBurned":
                cal_dd[date] += int(float(value))
            elif rtype == "HKQuantityTypeIdentifierDistanceWalkingRunning":
                dist_dd[date] += float(value)
            elif rtype == "HKQuantityTypeIdentifierFlightsClimbed":
                flights_dd[date] += int(float(value))
            elif rtype == "HKQuantityTypeIdentifierBodyMass":
                data["weight_entries"].append({"date": date, "kg": round(float(value), 1)})
        for workout in root.iter("Workout"):
            data["workouts"].append({
                "type": workout.get("workoutActivityType", "").replace("HKWorkoutActivityType", ""),
                "duration_min": round(float(workout.get("duration", "0"))),
                "calories_burned": int(float(workout.get("totalEnergyBurned", "0"))),
                "date": workout.get("startDate", "")[:10],
            })
        data["steps_by_day"] = dict(steps_dd)
        data["calories_by_day"] = dict(cal_dd)
        data["distance_by_day"] = {k: round(v, 2) for k, v in dist_dd.items()}
        data["flights_by_day"] = dict(flights_dd)
    except Exception as e:
        data["error"] = str(e)
    return data

# Auto-load Apple Health data from local export
HEALTH_ZIP = "/Users/shravya/Downloads/export.zip"
if st.session_state.apple_health is None:
    if os.path.exists(HEALTH_ZIP):
        with st.spinner("🍎 Loading Apple Health data via Airbyte connector..."):
            st.session_state.apple_health = parse_apple_health(HEALTH_ZIP)
    else:
        st.session_state.apple_health = {"imported": False}
ah = st.session_state.apple_health

# ── Run Pipeline ───────────────────────────────────────────────────
if run_button:
    st.session_state.state = PipelineState()
    state = st.session_state.state
    progress_bar = st.progress(0); status = st.empty()
    orchestrator = Orchestrator()
    try:
        status.info("🔍 Searching recipes..."); progress_bar.progress(0.1)
        state.recipes = orchestrator.recipe_searcher.search_recipes(
            dietary_preferences=dietary_preferences, cuisine_preferences=cuisine_preferences, num_recipes=14)
        state.log(f"✅ Found {len(state.recipes)} recipes")
        if not state.recipes: st.error("No recipes found."); st.stop()
        progress_bar.progress(0.2)
        status.info("📅 Creating meal plan...")
        state.meal_plan = orchestrator.meal_planner.create_meal_plan(
            recipes=state.recipes, dietary_preferences=dietary_preferences,
            household_size=household_size, budget=budget, existing_ingredients=existing_list or None)
        state.log(f"✅ Meal plan: {len(state.meal_plan)} meals"); progress_bar.progress(0.35)
        status.info("🕸️ Building graph...")
        orchestrator.graph.clear_graph()
        for r in state.recipes: orchestrator.graph.add_recipe(r)
        for e in state.meal_plan:
            orchestrator.graph.schedule_recipe(e["day"], e["meal_type"], e["recipe_name"])
        state.log("✅ Graph built"); progress_bar.progress(0.5)
        status.info("🏪 Checking availability...")
        all_ings = list({i["name"].lower() for r in state.recipes for i in r.get("ingredients", [])})
        state.availability = orchestrator.availability_checker.check_availability(all_ings, location)
        for item in state.availability:
            orchestrator.graph.set_ingredient_availability(
                item["ingredient"], item.get("store","Local Grocery"), item.get("price",3.99), item.get("available",True))
        state.unavailable_items = [i["ingredient"] for i in state.availability if not i.get("available",True)]
        state.log(f"✅ {len(all_ings)-len(state.unavailable_items)}/{len(all_ings)} available"); progress_bar.progress(0.65)
        if state.unavailable_items:
            status.info("🔄 Adapting plan...")
            for ing in state.unavailable_items:
                affected = orchestrator.graph.get_affected_recipes(ing)
                if not affected: continue
                suggestion = orchestrator.meal_planner.suggest_substitution(ing, affected, dietary_preferences)
                state.adaptations.append({"ingredient": ing, "affected_recipes": affected, "suggestion": suggestion})
                if suggestion.get("action") == "substitute":
                    sub = suggestion.get("substitute_ingredient", "")
                    orchestrator.graph.add_substitution(ing, sub)
                    orchestrator.graph.set_ingredient_availability(sub, "Local Grocery", 3.99, True)
                    state.log(f"✅ '{ing}' → '{sub}'")
            state.log("✅ Adaptation complete")
        progress_bar.progress(0.8)
        status.info("🛒 Placing order...")
        state.shopping_list = orchestrator.graph.get_shopping_list()
        state.consolidated_order = orchestrator.order_placer.consolidate_order(
            state.shopping_list, household_size, existing_ingredients=existing_list or None)
        state.order_confirmation = orchestrator.order_placer.place_order(state.consolidated_order)
        state.log(f"✅ {state.order_confirmation.get('confirmation_message','Order placed!')}")
        progress_bar.progress(1.0); state.status = "complete"; status.success("✅ All done!")
    except Exception as e:
        state.status = "error"; state.error = str(e); st.error(f"Error: {e}")
    finally:
        try: orchestrator.close()
        except: pass

state = st.session_state.state

# ── Compute shared stats ───────────────────────────────────────────
summary = st.session_state.calorie_tracker.get_daily_summary(st.session_state.tracked_meals, targets)
workout_burned = sum(w.get("calories_burned", 0) for w in st.session_state.workouts)
remaining_cal = targets["calorie_target"] - summary["total_calories"] + workout_burned

# ── Helper: get last N days of health data ─────────────────────────
import plotly.graph_objects as go
from datetime import timedelta

def _week_data(ah_data, n=7):
    """Extract the last n days of Apple Health data."""
    today = datetime.now().strftime("%Y-%m-%d")
    dates = [(datetime.now() - timedelta(days=n-1-i)).strftime("%Y-%m-%d") for i in range(n)]
    labels = [(datetime.now() - timedelta(days=n-1-i)).strftime("%a %m/%d") for i in range(n)]
    steps = [ah_data.get("steps_by_day", {}).get(d, 0) for d in dates]
    cals = [ah_data.get("calories_by_day", {}).get(d, 0) for d in dates]
    dist = [ah_data.get("distance_by_day", {}).get(d, 0.0) for d in dates]
    flights = [ah_data.get("flights_by_day", {}).get(d, 0) for d in dates]
    return {"dates": dates, "labels": labels, "steps": steps, "cals": cals, "dist": dist, "flights": flights}

# ── HOME DASHBOARD (always visible) ───────────────────────────────
if not state or state.status not in ("complete", "error"):
    st.subheader(f"{'Welcome, ' + st.session_state.profile['name'] + '!' if st.session_state.profile['name'] else 'Welcome!'} {st.session_state.profile['avatar']}")

    # Quick stats row
    qs1, qs2, qs3, qs4, qs5 = st.columns(5)
    qs1.metric("🎯 Cal Target", f"{targets['calorie_target']}")
    qs2.metric("🔥 Consumed", f"{summary['total_calories']}")
    qs3.metric("🏋️ Burned", f"{workout_burned}")
    qs4.metric("💧 Water", f"{st.session_state.water_glasses}/8")
    qs5.metric("📊 Remaining", f"{remaining_cal}")

    # ── Apple Health Weekly Dashboard ──────────────────────────────
    if ah.get("imported"):
        week = _week_data(ah)
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_steps = ah.get("steps_by_day", {}).get(today_str, 0)
        today_cal = ah.get("calories_by_day", {}).get(today_str, 0)
        today_dist = ah.get("distance_by_day", {}).get(today_str, 0.0)
        today_flights = ah.get("flights_by_day", {}).get(today_str, 0)
        week_avg_steps = int(sum(week["steps"]) / max(len(week["steps"]), 1))

        st.divider()
        st.markdown("### 🍎 Apple Health — This Week")
        st.caption("Synced via **Airbyte** data connector")

        # Today's highlights
        t1, t2, t3, t4, t5 = st.columns(5)
        t1.metric("👟 Steps Today", f"{today_steps:,}", delta=f"{today_steps - week_avg_steps:+,} vs avg")
        t2.metric("🔥 Active Cal", f"{today_cal}")
        t3.metric("🚶 Distance", f"{today_dist:.1f} km")
        t4.metric("🏔️ Flights", f"{today_flights}")
        t5.metric("📊 Week Avg", f"{week_avg_steps:,} steps")

        # Charts row
        ch1, ch2 = st.columns(2)
        with ch1:
            # Steps bar chart
            step_colors = ["#4caf50" if s >= 10000 else "#ff9800" if s >= 5000 else "#f44336" for s in week["steps"]]
            fig_steps = go.Figure()
            fig_steps.add_trace(go.Bar(
                x=week["labels"], y=week["steps"], marker_color=step_colors,
                text=[f"{s:,}" for s in week["steps"]], textposition="outside", textfont_size=11))
            fig_steps.add_hline(y=10000, line_dash="dash", line_color="#4caf50", opacity=0.5,
                annotation_text="10K goal", annotation_position="top left")
            fig_steps.update_layout(
                title=dict(text="Daily Steps", font_size=16), height=320,
                margin=dict(t=40, b=20, l=20, r=20), yaxis_title=None, xaxis_title=None,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", yaxis=dict(gridcolor="#333"))
            st.plotly_chart(fig_steps, use_container_width=True)

        with ch2:
            # Active calories area chart
            fig_cal = go.Figure()
            fig_cal.add_trace(go.Scatter(
                x=week["labels"], y=week["cals"], mode="lines+markers+text",
                fill="tozeroy", fillcolor="rgba(255,107,53,0.15)",
                line=dict(color="#ff6b35", width=3), marker=dict(size=8, color="#ff6b35"),
                text=[str(c) for c in week["cals"]], textposition="top center", textfont_size=11))
            fig_cal.update_layout(
                title=dict(text="Active Calories Burned", font_size=16), height=320,
                margin=dict(t=40, b=20, l=20, r=20), yaxis_title=None, xaxis_title=None,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", yaxis=dict(gridcolor="#333"))
            st.plotly_chart(fig_cal, use_container_width=True)

        ch3, ch4 = st.columns(2)
        with ch3:
            # Distance bar chart
            fig_dist = go.Figure()
            fig_dist.add_trace(go.Bar(
                x=week["labels"], y=week["dist"],
                marker_color="#4fc3f7",
                text=[f"{d:.1f}" for d in week["dist"]], textposition="outside", textfont_size=11))
            fig_dist.update_layout(
                title=dict(text="Distance (km)", font_size=16), height=280,
                margin=dict(t=40, b=20, l=20, r=20), yaxis_title=None, xaxis_title=None,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", yaxis=dict(gridcolor="#333"))
            st.plotly_chart(fig_dist, use_container_width=True)

        with ch4:
            # Flights climbed chart
            fig_fl = go.Figure()
            fig_fl.add_trace(go.Bar(
                x=week["labels"], y=week["flights"],
                marker_color="#ffcc02",
                text=[str(f) for f in week["flights"]], textposition="outside", textfont_size=11))
            fig_fl.update_layout(
                title=dict(text="Flights Climbed", font_size=16), height=280,
                margin=dict(t=40, b=20, l=20, r=20), yaxis_title=None, xaxis_title=None,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="white", yaxis=dict(gridcolor="#333"))
            st.plotly_chart(fig_fl, use_container_width=True)

        # Weekly summary
        st.divider()
        ws1, ws2, ws3, ws4 = st.columns(4)
        ws1.metric("🏃 Week Total Steps", f"{sum(week['steps']):,}")
        ws2.metric("🔥 Week Total Cal", f"{sum(week['cals']):,}")
        ws3.metric("🚶 Week Distance", f"{sum(week['dist']):.1f} km")
        ws4.metric("🏔️ Week Flights", f"{sum(week['flights'])}")

    st.divider()
    dc1, dc2 = st.columns([2, 1])
    with dc1:
        st.markdown("### 🍽️ Quick Actions")
        st.info("👈 Configure your preferences in the sidebar and hit **Start Autonomous Planning** to generate your meal plan, build the ingredient graph, and place your grocery order.")
        if not ah.get("imported"):
            st.markdown("### 📱 Import Apple Health Data")
            st.caption("**Powered by Airbyte** — data connector for health data sync")
            health_file = st.file_uploader("Upload Apple Health export (xml or zip)", type=["xml", "zip"], key="health_upload")
            if health_file:
                with st.spinner("🔄 Importing via Airbyte data connector..."):
                    st.session_state.apple_health = parse_apple_health(health_file.read())
                    st.rerun()
    with dc2:
        st.markdown(f"""<div class="profile-card">
            <div style="font-size:3rem">{st.session_state.profile['avatar']}</div>
            <h3>{st.session_state.profile['name'] or 'Set your name →'}</h3>
            <p style="color:#888">{GOAL_PRESETS.get(goal,{}).get('label','')} • {activity_level}</p>
            <hr style="border-color:#333">
            <p>🔥 {targets['calorie_target']} cal/day</p>
            <p>💪 {targets['protein_target']}g protein</p>
            <p>📏 {height_cm}cm • ⚖️ {weight_kg}kg</p>
            <p>🔥 Streak: {st.session_state.streak_days} day(s)</p>
        </div>""", unsafe_allow_html=True)

# ── TABS (after pipeline runs) ─────────────────────────────────────
if state and state.status in ("complete", "error"):
    tab_home, tab_plan, tab_graph, tab_adapt, tab_order, tab_cal, tab_workout, tab_hydra, tab_log = st.tabs(
        ["🏠 Dashboard", "📅 Meal Plan", "🕸️ Graph", "🔄 Adapt", "🛒 Order",
         "🔥 Calories", "🏋️ Workouts", "💧 Hydration", "📋 Log"])

    # ── DASHBOARD TAB ──────────────────────────────────────────────
    with tab_home:
        name = st.session_state.profile["name"] or "Chef"
        st.subheader(f"{st.session_state.profile['avatar']} {name}'s Dashboard")

        # Top stats
        s1,s2,s3,s4,s5,s6 = st.columns(6)
        s1.metric("🎯 Target", f"{targets['calorie_target']}")
        s2.metric("🔥 Eaten", f"{summary['total_calories']}")
        s3.metric("🏋️ Burned", f"{workout_burned}")
        s4.metric("📊 Net Left", f"{remaining_cal}")
        s5.metric("💧 Water", f"{st.session_state.water_glasses}/8")
        s6.metric("🔥 Streak", f"{st.session_state.streak_days}d")

        # Progress bars
        st.divider()
        cal_pct = min(summary["total_calories"] / max(targets["calorie_target"],1), 1.0)
        st.progress(cal_pct, text=f"Calories: {summary['total_calories']} / {targets['calorie_target']}")
        pro_pct = min(summary["total_protein"] / max(targets["protein_target"],1), 1.0)
        st.progress(pro_pct, text=f"Protein: {summary['total_protein']}g / {targets['protein_target']}g")

        # Macro chart + Health Score side by side
        mc1, mc2 = st.columns([1,1])
        with mc1:
            st.markdown("### Macro Distribution")
            if summary["total_calories"] > 0:
                fig = go.Figure(data=[go.Pie(
                    labels=["Protein","Carbs","Fat"],
                    values=[summary["total_protein"]*4, summary["total_carbs"]*4, summary["total_fat"]*9],
                    marker_colors=["#ff6b35","#4fc3f7","#ffcc02"], hole=0.4, textinfo="label+percent")])
                fig.update_layout(showlegend=False, height=250, margin=dict(t=0,b=0,l=0,r=0),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Log meals to see macros.")
        with mc2:
            st.markdown("### Daily Health Score")
            meals_logged = len(st.session_state.tracked_meals)
            water = st.session_state.water_glasses
            hc = []
            if meals_logged > 0: hc.append(min(summary.get("avg_health_score",0)/10*40, 40))
            hc.append(max(0, 30 - abs(summary["total_calories"]-targets["calorie_target"])/max(targets["calorie_target"],1)*30))
            hc.append(min(water/8*30, 30))
            ds = sum(hc)
            sc = "#4caf50" if ds>=70 else "#ff9800" if ds>=40 else "#f44336"
            st.markdown(f'<p class="health-score-big" style="color:{sc}">{ds:.0f}/100</p>', unsafe_allow_html=True)
            st.caption("40% nutrition + 30% calories + 30% hydration")

        # Apple Health weekly in dashboard tab
        if ah.get("imported"):
            st.divider()
            st.markdown("### 🍎 Apple Health — Weekly Activity")
            week = _week_data(ah)
            hc1, hc2 = st.columns(2)
            with hc1:
                step_colors = ["#4caf50" if s >= 10000 else "#ff9800" if s >= 5000 else "#f44336" for s in week["steps"]]
                fig_s = go.Figure(go.Bar(x=week["labels"], y=week["steps"], marker_color=step_colors,
                    text=[f"{s:,}" for s in week["steps"]], textposition="outside", textfont_size=10))
                fig_s.add_hline(y=10000, line_dash="dash", line_color="#4caf50", opacity=0.5)
                fig_s.update_layout(title="Steps", height=280, margin=dict(t=35,b=10,l=10,r=10),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font_color="white", yaxis=dict(gridcolor="#333"))
                st.plotly_chart(fig_s, use_container_width=True)
            with hc2:
                fig_c = go.Figure(go.Scatter(x=week["labels"], y=week["cals"], mode="lines+markers+text",
                    fill="tozeroy", fillcolor="rgba(255,107,53,0.15)",
                    line=dict(color="#ff6b35", width=3), marker=dict(size=7, color="#ff6b35"),
                    text=[str(c) for c in week["cals"]], textposition="top center", textfont_size=10))
                fig_c.update_layout(title="Active Calories", height=280, margin=dict(t=35,b=10,l=10,r=10),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font_color="white", yaxis=dict(gridcolor="#333"))
                st.plotly_chart(fig_c, use_container_width=True)

        # Badges
        st.divider()
        st.markdown("### 🏆 Achievements")
        all_badges = [
            ("first_meal","🍽️ First Bite","Log first meal"), ("first_workout","🏋️ First Sweat","Log first workout"),
            ("three_meals","🥉 Hat Trick","3 meals/day"), ("calorie_goal","🎯 On Target","Hit cal goal"),
            ("hydration_hero","💧 Hydrated","8 glasses"), ("health_80","⭐ Star","Score > 80"),
        ]
        if meals_logged >= 3 and "three_meals" not in st.session_state.badges: st.session_state.badges.append("three_meals")
        if water >= 8 and "hydration_hero" not in st.session_state.badges: st.session_state.badges.append("hydration_hero")
        if ds >= 80 and "health_80" not in st.session_state.badges: st.session_state.badges.append("health_80")
        bcols = st.columns(len(all_badges))
        for i,(bid,name,desc) in enumerate(all_badges):
            cls = "badge-earned" if bid in st.session_state.badges else "badge-locked"
            with bcols[i]:
                st.markdown(f'<div class="badge {cls}">{name}</div>', unsafe_allow_html=True)
                st.caption(desc)

    # ── MEAL PLAN TAB ──────────────────────────────────────────────
    with tab_plan:
        if state.meal_plan:
            days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            plan_by_day = {}
            for e in state.meal_plan: plan_by_day.setdefault(e.get("day","?"), []).append(e)
            for day in days:
                if day in plan_by_day:
                    st.subheader(f"📆 {day}")
                    cols = st.columns(3)
                    order = {"breakfast":0,"lunch":1,"dinner":2}
                    for e in sorted(plan_by_day[day], key=lambda x: order.get(x.get("meal_type",""),3)):
                        emoji = {"breakfast":"🌅","lunch":"☀️","dinner":"🌙"}.get(e.get("meal_type",""),"🍽️")
                        with cols[order.get(e.get("meal_type",""),0)]:
                            st.markdown(f'<div class="meal-card"><h4>{emoji} {e.get("meal_type","").title()}</h4>'
                                f'<p><strong>{e.get("recipe_name","TBD")}</strong></p></div>', unsafe_allow_html=True)

    # ── GRAPH TAB ──────────────────────────────────────────────────
    with tab_graph:
        st.subheader("🕸️ Interactive Ingredient Graph")
        if state.recipes:
            from pyvis.network import Network
            net = Network(height="500px", width="100%", bgcolor="#0e1117", font_color="white")
            net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=150)
            added_r, added_i, ic = set(), set(), {}
            for r in state.recipes:
                for i in r.get("ingredients",[]): n=i["name"].lower(); ic[n]=ic.get(n,0)+1
            for r in state.recipes:
                rn = r["name"]
                if rn not in added_r:
                    net.add_node(rn, label=rn, color="#ff6b35", shape="box", size=20, title=f"🍳 {rn}"); added_r.add(rn)
                for i in r.get("ingredients",[]):
                    n=i["name"].lower(); owned=n in existing_list; cnt=ic.get(n,1); sz=10+cnt*5
                    clr="#ffd700" if owned else ("#00ff88" if cnt>=2 else "#4fc3f7")
                    if n not in added_i:
                        net.add_node(n, label=f"✓ {n}" if owned else n, color=clr, size=sz,
                            title=f"{'🏠 Owned | ' if owned else ''}{cnt} recipe(s)"); added_i.add(n)
                    net.add_edge(rn, n, color="#555555")
            components.html(net.generate_html(), height=520, scrolling=False)
            st.markdown("**Legend:** 🟧 Recipe • 🟢 Shared • 🔵 Ingredient • 🟡 Owned")

    # ── ADAPT TAB ──────────────────────────────────────────────────
    with tab_adapt:
        if state.adaptations:
            for a in state.adaptations:
                with st.expander(f"⚠️ {a['ingredient']}", expanded=True):
                    st.markdown(f"**Affected:** {', '.join(a['affected_recipes'])}")
                    s = a.get("suggestion",{})
                    if s.get("action")=="substitute": st.success(f"✅ → **{s.get('substitute_ingredient','?')}**")
                    elif s.get("action")=="replace": st.success(f"✅ New: **{s.get('replacement_recipe',{}).get('name','?')}**")
                    st.caption(s.get("reasoning",""))
        else: st.success("✅ All ingredients available!")

    # ── ORDER TAB ──────────────────────────────────────────────────
    with tab_order:
        if state.order_confirmation:
            c = state.order_confirmation
            st.markdown(f'<div class="order-card"><h3>✅ Order Confirmed!</h3>'
                f'<p><b>ID:</b> {c.get("order_id","")}</p>'
                f'<p><b>Items:</b> {c.get("item_count",0)} • <b>Total:</b> ${c.get("total",0):.2f}</p>'
                f'<p><b>Stores:</b> {", ".join(c.get("stores",[]))}</p>'
                f'<p><b>Delivery:</b> {c.get("estimated_delivery","")}</p></div>', unsafe_allow_html=True)
        if state.consolidated_order and state.consolidated_order.get("stores"):
            if existing_list: st.info(f"🏠 Skipped: **{', '.join(existing_list)}**")
            for store in state.consolidated_order["stores"]:
                with st.expander(f"🏪 {store.get('name','')} — ${store.get('subtotal',0):.2f}", expanded=True):
                    for item in store.get("items",[]):
                        c1,c2,c3 = st.columns([3,1,1])
                        c1.write(f"🥬 {item.get('ingredient','')}"); c2.write(item.get("quantity","1"))
                        c3.write(f"${item.get('price',0):.2f}")
            if state.consolidated_order.get("savings_tips"): st.info(f"💡 {state.consolidated_order['savings_tips']}")

    # ── CALORIE TRACKER TAB ────────────────────────────────────────
    with tab_cal:
        st.subheader("🔥 Calorie Tracker")
        st.markdown(f"**Budget:** {targets['calorie_target']} cal • **Remaining:** "
                    f"{'🟢' if remaining_cal>0 else '🔴'} {remaining_cal} cal (incl. workout burn)")
        cup, cres = st.columns([1,1])
        with cup:
            uploaded_img = st.file_uploader("📸 Meal photo", type=["jpg","jpeg","png","webp"], key="cal_img")
            if uploaded_img: st.image(uploaded_img, caption="Your meal", use_container_width=True)
            meal_desc = st.text_area("📝 Describe meal", placeholder="Grilled chicken with rice", height=80)
            analyze_btn = st.button("🔍 Analyze", type="primary", use_container_width=True,
                disabled=not(uploaded_img or meal_desc))
        if analyze_btn and (uploaded_img or meal_desc):
            with st.spinner("Analyzing..."):
                img_bytes = uploaded_img.read() if uploaded_img else None
                result = st.session_state.calorie_tracker.analyze_meal(
                    image_bytes=img_bytes, description=meal_desc, goal=goal, remaining_calories=remaining_cal)
                st.session_state.tracked_meals.append(result)
                if len(st.session_state.tracked_meals)==1 and "first_meal" not in st.session_state.badges:
                    st.session_state.badges.append("first_meal"); st.toast("🏆 First Meal Logged!")
        with cres:
            if st.session_state.tracked_meals:
                latest = st.session_state.tracked_meals[-1]
                st.markdown(f"### 🍽️ {latest.get('meal_name','')}")
                m1,m2,m3,m4 = st.columns(4)
                m1.metric("🔥", latest.get("total_calories",0)); m2.metric("💪", f"{latest.get('total_protein',0)}g")
                m3.metric("🍞", f"{latest.get('total_carbs',0)}g"); m4.metric("🥑", f"{latest.get('total_fat',0)}g")
                if latest.get("sodium_warning"): st.warning("⚠️ High sodium!")
                if latest.get("sugar_warning"): st.warning("⚠️ High sugar!")
                if latest.get("items"):
                    for item in latest["items"]:
                        st.markdown(f"- **{item.get('name','?')}** ({item.get('portion','?')}) — {item.get('calories',0)} cal")
                if latest.get("notes"): st.info(f"💡 {latest['notes']}")
            else: st.info("Upload a photo or describe your meal.")
        if st.session_state.tracked_meals:
            st.divider()
            for meal in reversed(st.session_state.tracked_meals):
                with st.expander(f"{meal.get('meal_name','')} — {meal.get('total_calories',0)} cal"):
                    for item in meal.get("items",[]): st.write(f"- {item.get('name','?')}: {item.get('calories',0)} cal")
            if st.button("🗑️ Clear Meals"): st.session_state.tracked_meals=[]; st.rerun()

    # ── WORKOUT TAB ────────────────────────────────────────────────
    with tab_workout:
        st.subheader("🏋️ Workout Tracker")
        st.markdown(f"**Burned today:** 🔥 {workout_burned} cal")
        st.divider()
        wc1, wc2 = st.columns(2)
        with wc1:
            wtype = st.selectbox("Type", ["🏃 Running","🚶 Walking","🚴 Cycling","🏊 Swimming",
                "🏋️ Weights","🧘 Yoga","🤸 HIIT","🥊 Boxing","🎾 Sports","🏔️ Hiking","Other"])
            dur = st.number_input("Minutes", 5, 300, 30, 5)
        with wc2:
            intensity = st.select_slider("Intensity", ["Light","Moderate","Intense","Very Intense"])
            cpm = {"Light":4,"Moderate":7,"Intense":10,"Very Intense":14}
            est = int(dur * cpm.get(intensity,7) * (weight_kg/70))
            cburn = st.number_input("Calories burned", 0, 5000, est, 10)
        wnotes = st.text_input("Notes", placeholder="e.g., 5K run")
        if st.button("✅ Log Workout", type="primary", use_container_width=True):
            st.session_state.workouts.append({"type":wtype,"duration_min":dur,"intensity":intensity,
                "calories_burned":cburn,"notes":wnotes,"logged_at":datetime.now().strftime("%Y-%m-%d %H:%M")})
            if len(st.session_state.workouts)==1 and "first_workout" not in st.session_state.badges:
                st.session_state.badges.append("first_workout"); st.toast("🏆 First Workout!")
            st.rerun()
        if st.session_state.workouts:
            st.divider()
            for w in reversed(st.session_state.workouts):
                wc = st.columns([2,1,1,1,2])
                wc[0].write(w["type"]); wc[1].write(f"{w['duration_min']}m")
                wc[2].write(w["intensity"]); wc[3].write(f"🔥{w['calories_burned']}")
                wc[4].write(w.get("notes",""))
            st.divider()
            nc1,nc2,nc3 = st.columns(3)
            nc1.metric("Consumed", f"{summary['total_calories']} cal")
            nc2.metric("Burned", f"-{workout_burned} cal")
            nc3.metric("Net", f"{summary['total_calories']-workout_burned} cal")
            if st.button("🗑️ Clear Workouts"): st.session_state.workouts=[]; st.rerun()

    # ── HYDRATION TAB ──────────────────────────────────────────────
    with tab_hydra:
        st.subheader("💧 Hydration Tracker")
        hgoal = st.slider("Daily goal (glasses)", 4, 16, 8)
        w = st.session_state.water_glasses
        st.markdown(f"### {w} / {hgoal} glasses")
        st.progress(min(w/hgoal,1.0))
        gcols = st.columns(8)
        for i in range(8):
            with gcols[i]:
                if st.button("🥛" if i<w else "🫗", key=f"g_{i}", use_container_width=True):
                    st.session_state.water_glasses=i+1; st.rerun()
        bc = st.columns(3)
        with bc[0]:
            if st.button("➕ Add", use_container_width=True): st.session_state.water_glasses+=1; st.rerun()
        with bc[1]:
            if st.button("➖ Remove", use_container_width=True): st.session_state.water_glasses=max(0,w-1); st.rerun()
        with bc[2]:
            if st.button("🔄 Reset", use_container_width=True): st.session_state.water_glasses=0; st.rerun()
        if w>=hgoal: st.success("🎉 Hydration goal met!"); st.balloons()
        elif w>0: st.info(f"{hgoal-w} more glass(es) to go!")

    # ── LOG TAB ────────────────────────────────────────────────────
    with tab_log:
        st.subheader("📋 Agent Log")
        for i,log in enumerate(state.logs):
            st.markdown(f'<div class="log-entry">[{i+1}] {log}</div>', unsafe_allow_html=True)
        if state.error: st.error(state.error)

# ── FLOATING CHATBOT ───────────────────────────────────────────────
with st.expander("💬 Nutrition Assistant", expanded=st.session_state.chat_open):
    st.session_state.chat_open = True
    st.markdown(f"**{remaining_cal} cal remaining** (incl. workouts)")
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if prompt := st.chat_input("What should I eat?", key="chat_float"):
        st.session_state.chat_messages.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("..."):
                client = OpenAI(api_key=config.OPENAI_API_KEY)
                sys_msg = (
                    f"You are a friendly nutritionist chatbot. User stats:\n"
                    f"- Goal: {GOAL_PRESETS.get(goal,{}).get('label',goal)}\n"
                    f"- Cal target: {targets['calorie_target']}, consumed: {summary['total_calories']}, "
                    f"remaining: {remaining_cal} (incl {workout_burned} burned)\n"
                    f"- Protein left: {targets['protein_target']-summary['total_protein']}g\n"
                    f"- Preferences: {dietary_preferences}, Cuisine: {cuisine_preferences}\n"
                    "Suggest specific meals with calories. Be concise and encouraging."
                )
                msgs = [{"role":"system","content":sys_msg}]
                for m in st.session_state.chat_messages[-10:]:
                    msgs.append({"role":m["role"],"content":m["content"]})
                resp = client.chat.completions.create(model=config.OPENAI_MODEL, messages=msgs, temperature=0.7, max_tokens=400)
                reply = resp.choices[0].message.content.strip()
                st.markdown(reply)
                st.session_state.chat_messages.append({"role":"assistant","content":reply})
    if st.session_state.chat_messages:
        if st.button("🗑️ Clear Chat", key="clr_chat"): st.session_state.chat_messages=[]; st.rerun()
