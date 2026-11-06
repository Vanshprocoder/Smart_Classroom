
import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime


# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="Smart Classroom Dashboard",
    page_icon="🏫",
    layout="wide"
)

API_URL = "http://127.0.0.1:8000"

REQUEST_TIMEOUT = 300


# ==================================================
# 2. CUSTOM STYLING
# ==================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 30px;
        font-weight: 700;
    }

    .sub-title {
        color: #777;
        font-size: 15px;
    }

    .report-box {
        padding: 20px;
        border-radius: 10px;
        background-color: rgba(128,128,128,0.08);
        border: 1px solid rgba(128,128,128,0.2);
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ==================================================
# 3. API FUNCTIONS
# ==================================================

def get_api_data(endpoint):

    try:

        response = requests.get(
            f"{API_URL}/{endpoint}",
            timeout=30
        )

        response.raise_for_status()

        return response.json()

    except requests.exceptions.RequestException as exc:

        st.error(
            f"Unable to connect to backend: {exc}"
        )

        return None


def generate_ai_report():

    try:

        with st.spinner(
            "Gemini AI is analysing classroom data. "
            "This may take a few minutes..."
        ):

            response = requests.post(
                f"{API_URL}/analyze",
                timeout=REQUEST_TIMEOUT
            )

            response.raise_for_status()

            return response.json()

    except requests.exceptions.Timeout:

        st.error(
            "The AI analysis request timed out after "
            f"{REQUEST_TIMEOUT} seconds. Check the "
            "FastAPI terminal before trying again."
        )

        return None

    except requests.exceptions.HTTPError as exc:

        error_message = "AI analysis failed."

        try:
            error_message = response.json().get(
                "detail",
                str(exc)
            )
        except Exception:
            error_message = str(exc)

        st.error(error_message)

        return None

    except requests.exceptions.RequestException as exc:

        st.error(
            f"Could not connect to the AI service: {exc}"
        )

        return None


# ==================================================
# 4. DASHBOARD HEADER
# ==================================================

st.markdown(
    '<div class="main-title">🏫 Smart Classroom Energy System</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">'
    'AI-powered classroom energy monitoring and automation'
    '</div>',
    unsafe_allow_html=True
)

st.divider()


# ==================================================
# 5. SIDEBAR
# ==================================================

st.sidebar.title("Smart Classroom")

st.sidebar.markdown(
    "### Navigation"
)

page = st.sidebar.radio(
    "Select Section",
    [
        "Dashboard",
        "Sensor History",
        "AI Energy Report"
    ]
)

st.sidebar.divider()

st.sidebar.caption(
    "ESP32 + Firebase + Gemini AI"
)

st.sidebar.caption(
    "Smart Energy Conservation Project"
)


# ==================================================
# 6. FETCH SENSOR DATA
# ==================================================

api_data = get_api_data("readings")

if api_data is None:
    st.stop()

readings = api_data.get("readings", [])

if not readings:

    st.warning(
        "No sensor readings available yet. "
        "Check whether the ESP32 is sending data."
    )

    st.stop()


df = pd.DataFrame(readings)

if "received_at" in df.columns:

    df["received_at"] = pd.to_datetime(
        df["received_at"],
        unit="s",
        errors="coerce",
        utc=True
    )

    df = df.sort_values(
        "received_at",
        ascending=True
    )

for column in ["motion", "dark", "light_on"]:

    if column in df.columns:

        df[column] = (
            df[column]
            .fillna(False)
            .astype(bool)
        )


# ==================================================
# 7. CALCULATE METRICS
# ==================================================

total_readings = len(df)

motion_count = int(
    df["motion"].sum()
) if "motion" in df else 0

dark_count = int(
    df["dark"].sum()
) if "dark" in df else 0

light_on_count = int(
    df["light_on"].sum()
) if "light_on" in df else 0

light_off_count = (
    total_readings - light_on_count
)

light_on_percentage = round(
    (light_on_count / total_readings) * 100,
    1
) if total_readings else 0


# ==================================================
# 8. DASHBOARD PAGE
# ==================================================

if page == "Dashboard":

    st.subheader("Classroom Overview")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Readings",
        total_readings
    )

    col2.metric(
        "Motion Detected",
        motion_count
    )

    col3.metric(
        "Dark Conditions",
        dark_count
    )

    col4.metric(
        "Light ON Readings",
        light_on_count
    )

    st.divider()

    st.subheader("Lighting Status")

    col1, col2 = st.columns(2)

    col1.metric(
        "Light ON",
        light_on_count
    )

    col2.metric(
        "Light OFF",
        light_off_count
    )

    if total_readings:

        st.progress(
            min(light_on_percentage / 100, 1.0),
            text=f"Light ON in {light_on_percentage}% of readings"
        )

    st.divider()

    st.subheader("Sensor Activity")

    chart_df = df.copy()

    if "received_at" in chart_df.columns:

        chart_df = chart_df.dropna(
            subset=["received_at"]
        )

        if not chart_df.empty:

            activity_columns = [
                column
                for column in ["motion", "dark", "light_on"]
                if column in chart_df.columns
            ]

            if activity_columns:

                chart_data = chart_df[
                    ["received_at"] + activity_columns
                ].melt(
                    id_vars="received_at",
                    var_name="Sensor",
                    value_name="Status"
                )

                chart_data["Status"] = (
                    chart_data["Status"]
                    .astype(int)
                )

                fig = px.line(
                    chart_data,
                    x="received_at",
                    y="Status",
                    color="Sensor",
                    title="Sensor Activity Over Time",
                    markers=True
                )

                fig.update_layout(
                    yaxis=dict(
                        tickmode="array",
                        tickvals=[0, 1],
                        ticktext=["OFF / No", "ON / Yes"]
                    ),
                    xaxis_title="Time",
                    yaxis_title="Sensor State"
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

    st.divider()

    st.subheader("Latest Sensor Readings")

    st.dataframe(
        df.tail(10).sort_values(
            "received_at",
            ascending=False
        ) if "received_at" in df.columns else df.tail(10),
        use_container_width=True,
        hide_index=True
    )

    if st.button(
        "🔄 Refresh Dashboard",
        use_container_width=True
    ):

        st.rerun()


# ==================================================
# 9. SENSOR HISTORY PAGE
# ==================================================

elif page == "Sensor History":

    st.subheader("Complete Sensor History")

    st.write(
        f"Showing {len(df)} readings retrieved from Firebase."
    )

    st.dataframe(
        df.sort_values(
            "received_at",
            ascending=False
        ) if "received_at" in df.columns else df,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    st.subheader("Sensor Distribution")

    distribution = pd.DataFrame({
        "Sensor": [
            "Motion Detected",
            "Dark Conditions",
            "Light ON"
        ],
        "Count": [
            motion_count,
            dark_count,
            light_on_count
        ]
    })

    fig = px.bar(
        distribution,
        x="Sensor",
        y="Count",
        title="Sensor Reading Distribution",
        text="Count"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    if st.button("Refresh History"):

        st.rerun()


# ==================================================
# 10. AI ENERGY REPORT PAGE
# ==================================================

elif page == "AI Energy Report":

    st.subheader("🤖 AI Energy Analysis")

    st.write(
        "Generate an intelligent report based on "
        "the classroom sensor readings."
    )

    st.info(
        "Gemini AI analyses the overall sensor statistics "
        "and a sample of recent readings. Generation may "
        "take a few minutes."
    )

    col1, col2 = st.columns(2)

    col1.metric(
        "Total Records",
        total_readings
    )

    col2.metric(
        "Light ON Percentage",
        f"{light_on_percentage}%"
    )

    st.divider()

    if st.button(
        "✨ Generate AI Energy Report",
        type="primary",
        use_container_width=True
    ):

        result = generate_ai_report()

        if result and result.get("success"):

            st.session_state["latest_ai_report"] = result

            st.success(
                "AI energy report generated successfully!"
            )

    # Display the latest generated report
    result = st.session_state.get(
        "latest_ai_report"
    )

    if result:

        st.divider()

        st.subheader("Generated Energy Report")

        st.caption(
            f"Model: {result.get('model', 'Gemini')} "
            f"| Records analysed: "
            f"{result.get('readings_analyzed', 'N/A')}"
        )

        st.markdown(
            '<div class="report-box">',
            unsafe_allow_html=True
        )

        st.markdown(
            result.get(
                "report",
                "No report content available."
            )
        )

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

        statistics = result.get(
            "statistics",
            {}
        )

        if statistics:

            st.divider()

            st.subheader("Analysis Statistics")

            stat1, stat2, stat3 = st.columns(3)

            stat1.metric(
                "Motion",
                statistics.get("motion_count", 0),
                f"{statistics.get('motion_percentage', 0)}%"
            )

            stat2.metric(
                "Dark",
                statistics.get("dark_count", 0),
                f"{statistics.get('dark_percentage', 0)}%"
            )

            stat3.metric(
                "Light ON",
                statistics.get("light_on_count", 0),
                f"{statistics.get('light_on_percentage', 0)}%"
            )

    # Fetch previously saved reports
    st.divider()

    with st.expander("View Previous AI Reports"):

        previous_data = get_api_data("reports")

        if previous_data:

            previous_reports = previous_data.get(
                "reports",
                []
            )

            if previous_reports:

                for report in previous_reports:

                    report_date = report.get(
                        "created_at",
                        "Unknown date"
                    )

                    st.markdown(
                        f"**Report generated:** {report_date}"
                    )

                    st.markdown(
                        report.get("report", "")
                    )

                    st.divider()

            else:

                st.info(
                    "No previous AI reports found."
                )
