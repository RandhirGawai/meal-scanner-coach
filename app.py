"""
app.py
------
AI Meal Scanner + Body Recomposition Coach
A free, local-first Streamlit app for tracking meals (via AI photo analysis),
body composition, and activity — with AI-generated recomposition coaching.

Run with:  streamlit run app.py
"""

import streamlit as st
from datetime import date, datetime
from PIL import Image

import database as db
import ai_engine
import utils

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Meal Scanner & Recomp Coach",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()

# Light custom styling — mobile-friendly, clean cards
st.markdown("""
<style>
    .main > div { padding-top: 1rem; }
    .metric-card {
        background: #f7f9fb; border-radius: 14px; padding: 1rem 1.2rem;
        border: 1px solid #eaecef; margin-bottom: 0.6rem;
    }
    .food-chip {
        display: inline-block; background: #eef5ff; color: #1a4d8f;
        padding: 3px 10px; border-radius: 999px; font-size: 0.85rem;
        margin: 2px 4px 2px 0;
    }
    .verdict-box {
        background: linear-gradient(135deg, #e8f5e9, #f1f8e9);
        border-left: 4px solid #4caf50; border-radius: 8px;
        padding: 1rem 1.2rem; margin-bottom: 1rem;
    }
    .tip-box {
        background: linear-gradient(135deg, #fff8e1, #fffde7);
        border-left: 4px solid #ffa726; border-radius: 8px;
        padding: 1rem 1.2rem; margin-bottom: 1rem;
    }
    h1, h2, h3 { font-weight: 700; }
</style>
""", unsafe_allow_html=True)

TODAY = date.today().isoformat()

if "selected_date" not in st.session_state:
    st.session_state.selected_date = date.today()

# ---------------------------------------------------------------------------
# Sidebar — profile / settings
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🥗 Recomp Coach")
    st.caption("Free, local-first meal scanner & AI coach")

    if not ai_engine.GROQ_API_KEY and not ai_engine.USE_OLLAMA_FALLBACK:
        st.error("⚠️ No GROQ_API_KEY set. Add it to `.env`, or set "
                  "`USE_OLLAMA_FALLBACK=true` for offline mode.")

    st.divider()
    st.subheader("👤 Your Profile")

    profile = db.get_profile() or {}
    with st.form("profile_form"):
        name = st.text_input("Name", value=profile.get("name", ""))
        col1, col2 = st.columns(2)
        with col1:
            sex = st.selectbox("Sex", ["male", "female"],
                                index=0 if profile.get("sex", "male") == "male" else 1)
            age = st.number_input("Age", min_value=10, max_value=100,
                                   value=int(profile.get("age") or 28))
        with col2:
            height_cm = st.number_input("Height (cm)", min_value=100.0, max_value=250.0,
                                         value=float(profile.get("height_cm") or 170.0))
            target_weight = st.number_input("Target weight (kg)", min_value=30.0, max_value=200.0,
                                             value=float(profile.get("target_weight_kg") or 70.0))

        goal = st.selectbox(
            "Primary goal", ["recomposition", "fat_loss", "muscle_gain"],
            index=["recomposition", "fat_loss", "muscle_gain"].index(profile.get("goal", "recomposition")),
            format_func=lambda g: {"recomposition": "Lose fat + build muscle",
                                    "fat_loss": "Fat loss priority",
                                    "muscle_gain": "Muscle gain priority"}[g],
        )
        activity_level = st.selectbox(
            "Activity level",
            ["sedentary", "light", "moderate", "active", "very_active"],
            index=["sedentary", "light", "moderate", "active", "very_active"].index(
                profile.get("activity_level", "moderate")),
            format_func=lambda a: {"sedentary": "Sedentary (desk job, no exercise)",
                                    "light": "Light (1-3 workouts/week)",
                                    "moderate": "Moderate (3-5 workouts/week)",
                                    "active": "Active (6-7 workouts/week)",
                                    "very_active": "Very active (2x/day or physical job)"}[a],
        )
        protein_per_kg = st.slider("Protein target (g per kg bodyweight)", 1.2, 2.6,
                                    value=float(profile.get("protein_per_kg") or 2.0), step=0.1)

        if st.form_submit_button("💾 Save Profile", use_container_width=True):
            db.save_profile(name, sex, age, height_cm, goal, activity_level,
                             target_weight, protein_per_kg)
            st.success("Profile saved!")
            st.rerun()

    st.divider()
    st.caption("📅 Viewing data for:")
    st.session_state.selected_date = st.date_input(
        "Date", value=st.session_state.selected_date, label_visibility="collapsed"
    )

sel_date = st.session_state.selected_date.isoformat()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_scan, tab_body, tab_activity, tab_insights, tab_history = st.tabs(
    ["📸 Scan Meal", "⚖️ Body Metrics", "🏃 Activity", "🧠 AI Insights", "📊 History"]
)

# ===========================================================================
# TAB 1 — MEAL SCANNER
# ===========================================================================
#
# Flow (tracked via st.session_state["scan_stage"]):
#   idle        -> user uploads/takes a photo and clicks Analyze
#   review      -> AI's result is shown; user confirms it's correct, or says
#                  it's wrong and switches to "correcting"
#   correcting  -> user types what the meal actually was; AI re-estimates
#                  macros from that text and goes back to "review"
#   manual      -> user skips the AI entirely and types in macros by hand
#   confirmed   -> final editable totals + Save button
# ---------------------------------------------------------------------------
with tab_scan:
    st.header("📸 Scan a Meal")
    st.caption(f"Logging for **{sel_date}**")

    if "scan_stage" not in st.session_state:
        st.session_state.scan_stage = "idle"

    col_input, col_result = st.columns([1, 1.3])

    with col_input:
        meal_type = st.selectbox("Meal type", ["Breakfast", "Lunch", "Dinner", "Snack"])
        source = st.radio("Image source", ["Upload photo", "Take photo"], horizontal=True)

        img_file = None
        if source == "Upload photo":
            img_file = st.file_uploader("Upload a meal photo", type=["jpg", "jpeg", "png", "webp"])
        else:
            img_file = st.camera_input("Take a photo of your meal")

        if img_file is not None:
            image = Image.open(img_file)
            st.image(image, caption="Meal photo", use_container_width=True)

            if st.button("🔍 Analyze with AI", type="primary", use_container_width=True):
                with st.spinner("Analyzing your meal... (few seconds on Groq's free tier)"):
                    try:
                        result = ai_engine.analyze_meal_image(image)
                        st.session_state["last_analysis"] = result
                        st.session_state["last_image"] = image
                        st.session_state["last_meal_type"] = meal_type
                        st.session_state["scan_stage"] = "review"
                    except RuntimeError as e:
                        st.error(str(e))

        st.caption("Analysis not even close? You can skip the AI entirely below.")
        if st.button("✍️ Enter meal manually (no photo needed)", use_container_width=True):
            st.session_state["last_analysis"] = {
                "is_food": True, "foods": [],
                "totals": {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "fiber_g": 0},
                "confidence": "High", "notes": "",
            }
            st.session_state["last_image"] = None
            st.session_state["last_meal_type"] = meal_type
            st.session_state["scan_stage"] = "manual"

    with col_result:
        stage = st.session_state.get("scan_stage", "idle")
        result = st.session_state.get("last_analysis")

        # ---- Stage: nothing analyzed yet -------------------------------
        if stage == "idle" or not result:
            st.info("Upload or take a photo, then click **Analyze with AI** to see the "
                     "breakdown here — or enter a meal manually with the button on the left.")

        # ---- Stage: AI just analyzed the photo, ask the user to confirm ----
        elif stage == "review":
            if not result.get("is_food", True):
                st.warning(f"🤔 This doesn't look like food. {result.get('notes', '')}")
                if st.button("✏️ Describe what it actually is", use_container_width=True):
                    st.session_state["scan_stage"] = "correcting"
                    st.rerun()
            else:
                conf = result.get("confidence", "Medium")
                conf_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(conf, "🟡")
                st.markdown(f"**Confidence: {conf_color} {conf}**")
                if result.get("notes"):
                    st.caption(f"ℹ️ {result['notes']}")

                st.markdown("**AI detected these foods:**")
                foods = result.get("foods", [])
                chips_html = "".join(
                    f'<span class="food-chip">{f["name"]} ({f.get("estimated_quantity","")})</span>'
                    for f in foods
                )
                st.markdown(chips_html or "*(none)*", unsafe_allow_html=True)

                totals = result.get("totals", {})
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Calories", utils.fmt(totals.get("calories")))
                c2.metric("Protein", utils.fmt(totals.get("protein_g"), "g"))
                c3.metric("Carbs", utils.fmt(totals.get("carbs_g"), "g"))
                c4.metric("Fat", utils.fmt(totals.get("fat_g"), "g"))
                c5.metric("Fiber", utils.fmt(totals.get("fiber_g"), "g"))

                st.markdown("##### Does this look correct?")
                col_yes, col_no = st.columns(2)
                if col_yes.button("✅ Yes, looks correct", type="primary", use_container_width=True):
                    st.session_state["scan_stage"] = "confirmed"
                    st.rerun()
                if col_no.button("✏️ No, let me correct it", use_container_width=True):
                    st.session_state["scan_stage"] = "correcting"
                    st.rerun()

        # ---- Stage: user said the AI got it wrong -> they describe it ----
        elif stage == "correcting":
            st.markdown("##### What was the meal actually?")
            st.caption("Describe the foods and quantities in your own words — the AI will "
                       "re-estimate the nutrition from your description instead of the photo.")

            prior_foods = ", ".join(f["name"] for f in result.get("foods", [])) if result else ""
            correction_text = st.text_area(
                "Meal description",
                value=prior_foods,
                placeholder="e.g. 2 whole wheat rotis, 1 bowl palak paneer (~150g paneer), "
                            "small side of jeera rice",
                height=100,
            )

            col_reanalyze, col_manual = st.columns(2)
            if col_reanalyze.button("🔄 Re-analyze with my correction", type="primary",
                                     use_container_width=True):
                if not correction_text.strip():
                    st.warning("Type a description first.")
                else:
                    with st.spinner("Re-estimating nutrition from your description..."):
                        try:
                            new_result = ai_engine.analyze_meal_text(correction_text)
                            st.session_state["last_analysis"] = new_result
                            st.session_state["scan_stage"] = "review"
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))
            if col_manual.button("✍️ Skip AI — enter macros myself", use_container_width=True):
                st.session_state["scan_stage"] = "manual"
                st.rerun()

        # ---- Stage: confirmed by AI, or fully manual -> final edit + save ----
        elif stage in ("confirmed", "manual"):
            if stage == "manual":
                st.markdown("##### Enter meal details manually")
            else:
                st.success("Great — fine-tune the numbers below if needed, then save.")

            foods = result.get("foods", [])
            totals = result.get("totals", {})

            if stage == "manual":
                food_names = st.text_input(
                    "Food items (comma-separated, optional but recommended)",
                    placeholder="e.g. 2 rotis, palak paneer, jeera rice"
                )
                foods = [{"name": n.strip(), "estimated_quantity": ""} for n in food_names.split(",") if n.strip()]

            c1, c2, c3, c4, c5 = st.columns(5)
            cal = c1.number_input("Calories", value=float(totals.get("calories", 0)), step=10.0)
            pro = c2.number_input("Protein (g)", value=float(totals.get("protein_g", 0)), step=1.0)
            carb = c3.number_input("Carbs (g)", value=float(totals.get("carbs_g", 0)), step=1.0)
            fat = c4.number_input("Fat (g)", value=float(totals.get("fat_g", 0)), step=1.0)
            fiber = c5.number_input("Fiber (g)", value=float(totals.get("fiber_g", 0)), step=1.0)

            user_notes = st.text_input("Notes (optional)", placeholder="e.g. added extra ghee")

            col_save, col_restart = st.columns([2, 1])
            if col_save.button("✅ Save Meal", type="primary", use_container_width=True):
                img = st.session_state.get("last_image")
                image_base64 = utils.image_to_base64(img) if img is not None else None
                confidence_label = "Manual entry" if stage == "manual" else result.get("confidence", "Medium")
                db.add_meal(
                    log_date=sel_date,
                    log_time=datetime.now().strftime("%H:%M"),
                    meal_type=st.session_state.get("last_meal_type", meal_type),
                    image_base64=image_base64,
                    foods=foods,
                    calories=cal, protein_g=pro, carbs_g=carb, fat_g=fat, fiber_g=fiber,
                    confidence=confidence_label,
                    ai_notes=result.get("notes", ""),
                    user_notes=user_notes,
                )
                st.success("Meal saved! 🎉")
                for key in ("last_analysis", "last_image", "last_meal_type"):
                    st.session_state.pop(key, None)
                st.session_state["scan_stage"] = "idle"
                st.rerun()
            if col_restart.button("↩️ Start over", use_container_width=True):
                for key in ("last_analysis", "last_image", "last_meal_type"):
                    st.session_state.pop(key, None)
                st.session_state["scan_stage"] = "idle"
                st.rerun()

    st.divider()
    st.subheader(f"Today's logged meals — {sel_date}")
    todays_meals = db.get_meals_for_date(sel_date)
    if not todays_meals:
        st.caption("No meals logged yet for this date.")
    else:
        for m in todays_meals:
            with st.expander(f"{m['meal_type']} · {m['log_time']} · {utils.fmt(m['calories'])} kcal"):
                col_a, col_b = st.columns([1, 2])
                with col_a:
                    if m.get("image_base64"):
                        try:
                            st.image(utils.image_from_base64(m["image_base64"]), use_container_width=True)
                        except Exception:
                            pass
                with col_b:
                    st.write(f"**Calories:** {utils.fmt(m['calories'])} kcal")
                    st.write(f"**Protein:** {utils.fmt(m['protein_g'], 'g')} · "
                             f"**Carbs:** {utils.fmt(m['carbs_g'], 'g')} · "
                             f"**Fat:** {utils.fmt(m['fat_g'], 'g')} · "
                             f"**Fiber:** {utils.fmt(m['fiber_g'], 'g')}")
                    if m["user_notes"]:
                        st.caption(f"Note: {m['user_notes']}")
                    if st.button("🗑️ Delete", key=f"del_{m['id']}"):
                        db.delete_meal(m["id"])
                        st.rerun()

        totals = db.get_daily_totals(sel_date)
        st.markdown("#### Day total")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Calories", utils.fmt(totals["calories"]))
        c2.metric("Protein", utils.fmt(totals["protein_g"], "g"))
        c3.metric("Carbs", utils.fmt(totals["carbs_g"], "g"))
        c4.metric("Fat", utils.fmt(totals["fat_g"], "g"))
        c5.metric("Fiber", utils.fmt(totals["fiber_g"], "g"))

# ===========================================================================
# TAB 2 — BODY METRICS
# ===========================================================================
with tab_body:
    st.header("⚖️ Body Metrics")
    st.caption(f"Logging for **{sel_date}**")

    existing = db.get_body_metrics_for_date(sel_date) or {}

    with st.form("body_metrics_form"):
        c1, c2 = st.columns(2)
        with c1:
            weight = st.number_input("Weight (kg)", min_value=20.0, max_value=250.0,
                                      value=float(existing.get("weight_kg") or 70.0), step=0.1)
            body_fat = st.number_input("Body fat %", min_value=3.0, max_value=60.0,
                                        value=float(existing.get("body_fat_pct") or 20.0), step=0.1)
            muscle = st.number_input("Muscle / lean mass (kg)", min_value=10.0, max_value=150.0,
                                      value=float(existing.get("muscle_kg") or 55.0), step=0.1)
        with c2:
            water = st.number_input("Water %", min_value=20.0, max_value=80.0,
                                     value=float(existing.get("water_pct") or 55.0), step=0.1)
            bone = st.number_input("Bone mass (kg) — optional", min_value=0.0, max_value=10.0,
                                    value=float(existing.get("bone_mass_kg") or 0.0), step=0.1)
            visceral = st.number_input("Visceral fat rating — optional", min_value=0.0, max_value=30.0,
                                        value=float(existing.get("visceral_fat") or 0.0), step=0.5)

        notes = st.text_area("Notes (optional)", value=existing.get("notes") or "")

        if st.form_submit_button("💾 Save Body Metrics", type="primary", use_container_width=True):
            db.upsert_body_metrics(sel_date, weight, body_fat, muscle, water,
                                    bone or None, visceral or None, notes)
            st.success("Body metrics saved!")
            st.rerun()

    # Quick trend chart
    st.divider()
    st.subheader("Recent trend")
    history = db.get_all_body_metrics(limit=30)[::-1]
    if len(history) >= 2:
        import pandas as pd
        df = pd.DataFrame(history)
        df["log_date"] = pd.to_datetime(df["log_date"])
        st.line_chart(df.set_index("log_date")[["weight_kg", "body_fat_pct", "muscle_kg"]])
    else:
        st.caption("Log at least 2 days of body metrics to see a trend chart.")

# ===========================================================================
# TAB 3 — ACTIVITY
# ===========================================================================
with tab_activity:
    st.header("🏃 Activity")
    st.caption(f"Logging for **{sel_date}**")

    existing_act = db.get_activity_for_date(sel_date) or {}

    with st.form("activity_form"):
        workout_desc = st.text_input(
            "Gym / workout description",
            value=existing_act.get("workout_desc") or "",
            placeholder="e.g. Push day - chest, shoulders, triceps - 55 min"
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            workout_minutes = st.number_input("Workout duration (min)", min_value=0.0, max_value=300.0,
                                                value=float(existing_act.get("workout_minutes") or 0.0), step=5.0)
        with c2:
            walk_minutes = st.number_input("Walking time (min)", min_value=0.0, max_value=500.0,
                                            value=float(existing_act.get("walk_minutes") or 0.0), step=5.0)
        with c3:
            steps = st.number_input("Steps (optional)", min_value=0, max_value=100000,
                                     value=int(existing_act.get("steps") or 0), step=500)

        act_notes = st.text_area("Notes (optional)", value=existing_act.get("notes") or "")

        if st.form_submit_button("💾 Save Activity", type="primary", use_container_width=True):
            db.upsert_activity(sel_date, workout_desc, workout_minutes, walk_minutes,
                                steps or None, act_notes)
            st.success("Activity saved!")
            st.rerun()

# ===========================================================================
# TAB 4 — AI INSIGHTS
# ===========================================================================
with tab_insights:
    st.header("🧠 AI Insights & Coaching")
    st.caption(f"Based on your data for **{sel_date}** plus recent history")

    profile = db.get_profile()
    latest_body = db.get_body_metrics_for_date(sel_date) or db.get_latest_body_metrics()

    # Deterministic quick targets (always available, no API call needed)
    targets = ai_engine.calculate_targets(profile, latest_body)
    if targets["calorie_target"]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Maintenance calories", utils.fmt(targets["maintenance_calories"], " kcal"))
        c2.metric("Your calorie target", utils.fmt(targets["calorie_target"], " kcal"))
        c3.metric("Your protein target", utils.fmt(targets["protein_target_g"], "g"))
    else:
        st.info(targets["note"])

    st.divider()

    if st.button("✨ Generate Today's AI Coaching", type="primary", use_container_width=True):
        with st.spinner("Your coach is reviewing your data..."):
            try:
                today_meals = db.get_meals_for_date(sel_date)
                today_body = db.get_body_metrics_for_date(sel_date)
                today_activity = db.get_activity_for_date(sel_date)
                recent_history = db.get_last_n_days_summary(7)

                insights = ai_engine.generate_insights(
                    profile, today_meals, today_body, today_activity, recent_history
                )
                st.session_state["last_insights"] = insights
            except RuntimeError as e:
                st.error(str(e))

    insights = st.session_state.get("last_insights")
    if insights:
        st.markdown(f"""<div class="verdict-box">
            <b>🍽️ Latest meal verdict:</b><br>{insights.get('meal_verdict','')}
        </div>""", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🔥 Calories")
            st.progress(utils.macro_bar_pct(
                insights.get("calories_so_far", 0), insights.get("daily_calorie_target", 1)) / 100)
            st.caption(f"{utils.fmt(insights.get('calories_so_far'))} / "
                       f"{utils.fmt(insights.get('daily_calorie_target'))} kcal "
                       f"({utils.fmt(insights.get('calories_remaining'))} kcal remaining)")
        with c2:
            st.markdown("##### 🥩 Protein")
            st.progress(utils.macro_bar_pct(
                insights.get("protein_so_far_g", 0), insights.get("daily_protein_target_g", 1)) / 100)
            st.caption(f"{utils.fmt(insights.get('protein_so_far_g'), 'g')} / "
                       f"{utils.fmt(insights.get('daily_protein_target_g'), 'g')} "
                       f"({utils.fmt(insights.get('protein_remaining_g'), 'g')} remaining)")

        st.markdown(f"""<div class="tip-box">
            <b>💡 Today's tip:</b><br>{insights.get('fat_loss_muscle_gain_tip','')}
        </div>""", unsafe_allow_html=True)

        st.markdown("##### 📈 Weekly trend")
        st.write(insights.get("weekly_trend_analysis", ""))

        st.markdown("##### 🎯 Summary")
        st.write(insights.get("overall_summary", ""))
    else:
        st.info("Click the button above to get personalized AI coaching based on today's meals, "
                 "body metrics, and activity.")

# ===========================================================================
# TAB 5 — HISTORY
# ===========================================================================
with tab_history:
    st.header("📊 History & Progress")

    n_days = st.slider("Show last N days", 7, 90, 14)
    summary = db.get_last_n_days_summary(n_days)

    import pandas as pd
    df = pd.DataFrame(summary)
    df["date"] = pd.to_datetime(df["date"])

    st.subheader("Weight & body fat trend")
    if df["weight_kg"].notna().sum() >= 2:
        st.line_chart(df.set_index("date")[["weight_kg"]])
    else:
        st.caption("Not enough weight data logged yet.")

    if df["body_fat_pct"].notna().sum() >= 2:
        st.line_chart(df.set_index("date")[["body_fat_pct"]])

    st.subheader("Calories & protein trend")
    st.bar_chart(df.set_index("date")[["calories"]])
    st.bar_chart(df.set_index("date")[["protein_g"]])

    st.subheader("Raw daily log")
    st.dataframe(
        df[["date", "weight_kg", "body_fat_pct", "muscle_kg", "calories",
            "protein_g", "carbs_g", "fat_g", "workout", "walk_minutes", "steps"]],
        use_container_width=True, hide_index=True,
    )

    st.subheader("All logged meals")
    all_meals = db.get_all_meals(200)
    if all_meals:
        meals_df = pd.DataFrame(all_meals)[
            ["log_date", "log_time", "meal_type", "calories", "protein_g",
             "carbs_g", "fat_g", "fiber_g", "confidence"]
        ]
        st.dataframe(meals_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No meals logged yet.")
