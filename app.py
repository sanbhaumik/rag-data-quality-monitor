"""
Streamlit App - RAG Source Monitor
Entry point for the Streamlit application with Chat UI and Health Dashboard.
"""

import streamlit as st
import logging
from datetime import datetime
from ingestion.embedder import is_collection_empty, run_ingestion
from rag.engine import query_stream

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="RAG Source Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

if "page" not in st.session_state:
    st.session_state.page = "Chat"


# === Sidebar ===
with st.sidebar:
    st.title("🔍 RAG Source Monitor")

    # Navigation
    st.subheader("Navigation")
    page = st.radio(
        "Select Page",
        ["Chat", "Health Dashboard"],
        index=0 if st.session_state.page == "Chat" else 1,
        label_visibility="collapsed"
    )
    st.session_state.page = page

    st.divider()

    # Ingestion controls
    st.subheader("Data Management")

    # Check if collection is empty
    collection_empty = is_collection_empty()

    if collection_empty:
        st.warning("⚠️ Knowledge base is empty")
        st.info("Run ingestion to populate the RAG system with source content.")

    # Re-ingest button
    if st.button("🔄 Re-ingest Sources", use_container_width=True):
        with st.spinner("Ingesting sources... This may take several minutes."):
            try:
                count = run_ingestion()
                st.success(f"✅ Ingestion complete! {count} chunks stored.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Ingestion failed: {str(e)}")
                logger.error(f"Ingestion error: {e}", exc_info=True)

    st.divider()

    # Info section
    st.subheader("About")
    st.markdown("""
    **RAG Source Monitor** combines:
    - 🤖 RAG Q&A with Ollama
    - 🔍 Source quality monitoring
    - 📧 Email alerts
    - 📊 Health dashboard
    """)

    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")


# === Main Content ===
if st.session_state.page == "Chat":
    # === Chat Page ===
    st.title("💬 Chat with Your Documents")
    st.markdown("Ask questions about Python, JavaScript, Machine Learning, and more!")

    # Check if knowledge base is empty
    if collection_empty:
        st.error("❌ Knowledge base is empty. Please run ingestion from the sidebar.")
        st.info("Click the **'Re-ingest Sources'** button in the sidebar to populate the knowledge base.")
        st.stop()

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Show sources if available
            if message["role"] == "assistant" and "sources" in message:
                with st.expander("📚 Sources", expanded=False):
                    for i, source in enumerate(message["sources"], 1):
                        st.markdown(f"""
                        **{i}. {source['title']}**
                        *{source['source_name']}*
                        [{source['url']}]({source['url']})
                        """)

    # Chat input
    if prompt := st.chat_input("Ask a question about your documents..."):
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            try:
                # Get streaming response
                answer_stream, sources = query_stream(prompt)

                # Stream the response
                for chunk in answer_stream:
                    full_response += chunk
                    message_placeholder.markdown(full_response + "▌")

                # Final response without cursor
                message_placeholder.markdown(full_response)

                # Display sources
                if sources:
                    with st.expander("📚 Sources", expanded=False):
                        for i, source in enumerate(sources, 1):
                            st.markdown(f"""
                            **{i}. {source['title']}**
                            *{source['source_name']}*
                            [{source['url']}]({source['url']})
                            """)

                # Add assistant message to chat history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "sources": sources
                })

            except Exception as e:
                error_msg = f"❌ Error generating response: {str(e)}"
                st.error(error_msg)
                logger.error(f"Query error: {e}", exc_info=True)

                # Add error to chat history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                    "sources": []
                })

    # Clear chat button at bottom
    st.divider()
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    with col2:
        st.caption(f"{len(st.session_state.messages)} messages")

elif st.session_state.page == "Health Dashboard":
    # === Health Dashboard Page ===
    st.title("📊 Source Health Dashboard")
    st.markdown("Monitor the health and quality of your RAG sources.")

    import config
    import pandas as pd
    from monitor.db import (
        get_alert_summary, get_active_alerts, get_check_history,
        get_latest_check_by_source, mark_alert_resolved
    )
    from monitor.scheduler import run_monitor_now, get_scheduler_status, start_scheduler, stop_scheduler

    try:
        # === Top Row: Overall Health Summary ===
        st.subheader("📊 Overall Health")

        # Get alert summary
        summary = get_alert_summary()

        # Get latest check per source
        latest_checks = get_latest_check_by_source()

        # Display metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            total_sources = len(config.SOURCE_SITES)
            st.metric("Total Sources", total_sources)

        with col2:
            st.metric("Active Alerts", summary['total_active'],
                     delta=f"-{summary['resolved_this_week']}" if summary['resolved_this_week'] > 0 else None,
                     delta_color="inverse")

        with col3:
            st.metric("⚠️ Warnings", summary['warning_count'])

        with col4:
            st.metric("🔴 Critical", summary['critical_count'])

        st.divider()

        # === Source Health Status ===
        st.subheader("🔍 Source Health Status")

        source_cols = st.columns(len(config.SOURCE_SITES))

        for idx, (source_key, source_config) in enumerate(config.SOURCE_SITES.items()):
            with source_cols[idx]:
                # Determine health status
                latest = latest_checks.get(source_key)

                if not latest:
                    status_icon = "⚪"
                    status_text = "Unknown"
                    status_color = "gray"
                elif latest['status'] == 'ok':
                    status_icon = "🟢"
                    status_text = "Healthy"
                    status_color = "green"
                elif latest['status'] == 'warning':
                    status_icon = "🟡"
                    status_text = "Warning"
                    status_color = "orange"
                else:  # error
                    status_icon = "🔴"
                    status_text = "Error"
                    status_color = "red"

                st.markdown(f"### {status_icon} {source_config['name']}")
                st.caption(f"Status: **:{status_color}[{status_text}]**")

                if latest:
                    last_check = datetime.fromisoformat(latest['last_check'])
                    time_ago = datetime.now() - last_check
                    if time_ago.seconds < 3600:
                        time_str = f"{time_ago.seconds // 60}m ago"
                    elif time_ago.days < 1:
                        time_str = f"{time_ago.seconds // 3600}h ago"
                    else:
                        time_str = f"{time_ago.days}d ago"

                    st.caption(f"Last check: {time_str}")
                else:
                    st.caption("No checks yet")

        st.divider()

        # === Active Alerts Section ===
        st.subheader("⚠️ Active Alerts")

        alerts = get_active_alerts()

        if alerts:
            # Create DataFrame for better display
            alert_data = []
            for alert in alerts:
                severity_icon = "🔴" if alert['severity'] == 'critical' else "⚠️"
                alert_data.append({
                    'Icon': severity_icon,
                    'Source': alert['source_key'],
                    'Check Type': alert['check_type'],
                    'Severity': alert['severity'],
                    'Message': alert['message'],
                    'Created': alert['created_at'],
                    'ID': alert['id']
                })

            df_alerts = pd.DataFrame(alert_data)

            # Display alerts with action buttons
            for idx, row in df_alerts.iterrows():
                col1, col2 = st.columns([5, 1])

                with col1:
                    if row['Severity'] == 'critical':
                        st.error(f"{row['Icon']} **{row['Source']}** ({row['Check Type']}): {row['Message']}")
                    else:
                        st.warning(f"{row['Icon']} **{row['Source']}** ({row['Check Type']}): {row['Message']}")

                with col2:
                    if st.button("✅ Resolve", key=f"resolve_{row['ID']}", use_container_width=True):
                        mark_alert_resolved(row['ID'])
                        st.success("Alert resolved!")
                        st.rerun()
        else:
            st.success("✅ No active alerts! All sources are healthy.")

        st.divider()

        # === Controls Section ===
        st.subheader("🎛️ Monitoring Controls")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**On-Demand Checks**")
            deep_diff = st.checkbox("Enable Deep Diff", value=False,
                                   help="Perform detailed content comparison (slower)")

            if st.button("🔄 Run Checks Now", use_container_width=True, type="primary"):
                with st.spinner("Running source quality checks... This may take a minute."):
                    try:
                        result = run_monitor_now(deep_diff=deep_diff)
                        st.success(f"✅ Checks complete! {result['total_checks']} checks performed.")

                        if result['alerts']:
                            st.info(f"Generated {len(result['alerts'])} new alerts.")
                            if result['email_sent']:
                                st.info("📧 Alert digest email sent.")
                        else:
                            st.success("No new issues detected!")

                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Check failed: {str(e)}")
                        logger.error(f"On-demand check error: {e}", exc_info=True)

        with col2:
            st.markdown("**Scheduler Control**")

            scheduler_status = get_scheduler_status()

            if scheduler_status['running']:
                st.info(f"⏰ Scheduler: **Running** (every {scheduler_status['interval_hours']}h)")

                if scheduler_status['next_run']:
                    next_run_str = scheduler_status['next_run'].strftime('%Y-%m-%d %H:%M:%S')
                    st.caption(f"Next run: {next_run_str}")

                if st.button("⏸️ Stop Scheduler", use_container_width=True):
                    stop_scheduler()
                    st.success("Scheduler stopped")
                    st.rerun()
            else:
                st.warning(f"⏸️ Scheduler: **Stopped**")
                st.caption(f"Default interval: {scheduler_status['interval_hours']} hours")

                if st.button("▶️ Start Scheduler", use_container_width=True):
                    start_scheduler()
                    st.success("Scheduler started!")
                    st.rerun()

        st.divider()

        # === Check History Section ===
        st.subheader("📜 Check History")

        # Filter controls
        col1, col2 = st.columns([1, 3])

        with col1:
            source_filter = st.selectbox(
                "Filter by Source",
                ["All Sources"] + list(config.SOURCE_SITES.keys())
            )

        # Get history
        if source_filter == "All Sources":
            history = get_check_history(limit=50)
        else:
            history = get_check_history(source_key=source_filter, limit=50)

        if history:
            # Create DataFrame
            df = pd.DataFrame(history)

            # Format columns
            df = df[['source_key', 'url', 'check_type', 'status', 'detail', 'checked_at']]
            df.columns = ['Source', 'URL', 'Check Type', 'Status', 'Detail', 'Checked At']

            # Color code status
            def color_status(val):
                if val == 'ok':
                    return 'background-color: #d4edda'
                elif val == 'warning':
                    return 'background-color: #fff3cd'
                else:  # error
                    return 'background-color: #f8d7da'

            # Display with styling
            st.dataframe(
                df.style.applymap(color_status, subset=['Status']),
                use_container_width=True,
                hide_index=True,
                height=400
            )

            # Export option
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"check_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No check history yet. Run monitoring checks to populate this section.")

    except Exception as e:
        st.error(f"❌ Error loading dashboard: {str(e)}")
        logger.error(f"Dashboard error: {e}", exc_info=True)
