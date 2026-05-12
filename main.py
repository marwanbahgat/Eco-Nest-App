import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime
import urllib.parse
import os
from dotenv import load_dotenv

load_dotenv()

# --- 1. Connection & Server Settings ---

BASEROW_TOKEN = os.getenv("BASEROW_TOKEN").strip() if os.getenv("BASEROW_TOKEN") else None
PUBLIC_URL = os.getenv("PUBLIC_URL")
BASEROW_URL = os.getenv("BASEROW_URL")

WORK_ORDERS_TABLE_ID = os.getenv("WORK_ORDERS_TABLE_ID")
JOB_DETAILS_TABLE_ID = os.getenv("JOB_DETAILS_TABLE_ID")
APARTMENTS_TABLE_ID = os.getenv("APARTMENTS_TABLE_ID")
EMPLOYEES_TABLE_ID = os.getenv("EMPLOYEES_TABLE_ID")


users_raw = os.getenv("APP_USERS", "")
USERS = {item.split(":")[0]: item.split(":")[1] for item in users_raw.split(",") if ":" in item}

UPLOAD_DIR = os.path.expanduser("~/EcoNest_Files/photos")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- 2. Helper Functions ---
@st.cache_data(ttl=300)
def get_baserow_rows(table_id):
    url = f"{BASEROW_URL}{table_id}/?user_field_names=true"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
       st.sidebar.error(f"Error {response.status_code}: {response.text}")
        
    return response.json().get('results', [])
    try:
        response = requests.get(url, headers=headers)
        return response.json().get('results', []) if response.status_code == 200 else []
    except:
        return []
def get_single_row(table_id, row_id):
    url = f"{BASEROW_URL}{table_id}/{row_id}/?user_field_names=true"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        return response.json() if response.status_code == 200 else None
    except:
        return None
def update_baserow_row(table_id, row_id, data):
    url = f"{BASEROW_URL}{table_id}/{row_id}/?user_field_names=true"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}", "Content-Type": "application/json"}
    response = requests.patch(url, headers=headers, json=data)
    return response.status_code

def create_baserow_row(table_id, data):
    url = f"{BASEROW_URL}{table_id}/?user_field_names=true"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=data)
    return response.json()

def get_apartment_details(apt_id):
    """Fetch a single apartment row from table 758 by its row ID."""
    url = f"{BASEROW_URL}{APARTMENTS_TABLE_ID}/{apt_id}/?user_field_names=true"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return {}

def get_status_value(status_field):
    """
    Safely extract the status string from a Baserow field.
    Baserow can return a single-select as either a plain string "Completed"
    OR a dict {"id": 1, "value": "Completed"} depending on the field type.
    This function handles both cases so comparisons never silently fail.
    """
    if isinstance(status_field, dict):
        return status_field.get('value', '')
    return status_field or ''

def sync_work_order_status(order_id, all_details):
    """
    Counts completed apartments for the given order from the local all_details
    list (which must already be patched to reflect the latest completion)
    and pushes the correct status to the Work Orders table.
    """
    related = [
        f for f in all_details
        if f.get('cwo') and str(f['cwo'][0]['id']) == str(order_id)
    ]

    if not related:
        return

    total = len(related)
    # ✅ Use get_status_value() so we handle both string and dict formats
    completed = sum(1 for f in related if get_status_value(f.get('status')) == 'Completed')

    if completed == 0:
        new_status = "In Progress"
    elif completed < total:
        new_status = "Partially Finished"
    else:
        new_status = "Finished"

    update_baserow_row(WORK_ORDERS_TABLE_ID, order_id, {"status": new_status})

def upload_file_to_baserow(file_bytes, filename):
    """Uploads a file to Baserow's file storage and returns the file object (with url)."""
    upload_url = "https://data.alfagrouptrading.eu/api/user-files/upload-file/"
    headers = {"Authorization": f"Token {BASEROW_TOKEN}"}
    files = {"file": (filename, file_bytes, "image/jpeg")}
    try:
        response = requests.post(upload_url, headers=headers, files=files)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None  # ✅ Dead code line that was here has been removed

# --- 3. UI Styles ---
st.set_page_config(page_title="EcoNest System", layout="wide")

st.markdown("""
    <style>
    .worker-header { text-align: center; margin-bottom: 30px; background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .order-id { font-size: 42px; font-weight: bold; color: #1A73E8; line-height: 1; }
    .order-date { font-size: 20px; color: #5f6368; margin-top: 10px; }
    .flat-card { background: white; padding: 25px; border-radius: 15px; border: 1px solid #e0e0e0; margin-bottom: 30px; }
    .main-card { background: white; padding: 20px; border-radius: 8px; border: 1px solid #dee2e6; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. Worker Interface (The Mobile View) ---
def show_worker_interface(order_id):
    current_order = get_single_row(WORK_ORDERS_TABLE_ID, order_id)

    if not current_order:
        st.error("Work order not found."); return

    order_display_id = current_order.get('sub_id', f"Order #{order_id}")
    order_date = current_order.get('date', str(datetime.now().date()))

    all_details = get_baserow_rows(JOB_DETAILS_TABLE_ID)
    related_flats = [f for f in all_details if f.get('cwo') and str(f['cwo'][0]['id']) == order_id]

    # Header
    st.markdown(f"""
        <div class="worker-header">
            <div class="order-id">{order_display_id}</div>
            <div class="order-date">📅 {order_date}</div>
        </div>
    """, unsafe_allow_html=True)

    st.subheader("🏠 Assigned Apartments List")

    for flat in related_flats:
        f_id = str(flat['id'])
        f_name = flat['apartment'][0]['value'] if flat.get('apartment') else "Unknown"
        # ✅ Use get_status_value() here too so display is also consistent
        f_status = get_status_value(flat.get('status', 'In Progress'))

        st.markdown(f'<div class="flat-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 5, 2])

        with c1:
            st.markdown(f"### {f_name}")
            if f_status == "Completed":
                st.success("✅ Done")
            else:
                st.warning(f"🕒 {f_status}")

        with c2:
            if f_status != "Completed":
                t1, t2 = st.columns(2)
                a_start = t1.text_input("Start Time", "09:00", key=f"s_{f_id}")
                a_end = t2.text_input("End Time", "11:00", key=f"e_{f_id}")
                notes = st.text_area("Worker Notes", key=f"n_{f_id}")

                st.write("**Photos Evidence**")
                p1, p2 = st.columns(2)
                f_before = p1.file_uploader("Before", accept_multiple_files=True, key=f"fb_{f_id}")
                f_after = p2.file_uploader("After", accept_multiple_files=True, key=f"fa_{f_id}")
            else:
                st.info("Task details are locked (Completed).")

        with c3:
            st.write("**Checklist:**")
            st.caption("✔️ Sheets\n✔️ Bathroom\n✔️ Kitchen\n✔️ Bins")
            st.divider()
            if f_status != "Completed":
                if st.button(f"Confirm Finish {f_name}", key=f"btn_{f_id}", type="primary"):

                    before_file_objects = []
                    for i, photo in enumerate(f_before or []):
                        with st.spinner(f"Uploading before photo {i+1}..."):
                            result = upload_file_to_baserow(photo.getvalue(), f"T{f_id}_B_{i}.jpg")
                            if result:
                                before_file_objects.append(result)

                    after_file_objects = []
                    for i, photo in enumerate(f_after or []):
                        with st.spinner(f"Uploading after photo {i+1}..."):
                            result = upload_file_to_baserow(photo.getvalue(), f"T{f_id}_A_{i}.jpg")
                            if result:
                                after_file_objects.append(result)

                    base_d = order_date.split(' ')[0]
                    up_payload = {
                        "actual_start_time": f"{base_d}T{a_start}:00Z",
                        "actual_end_time": f"{base_d}T{a_end}:00Z",
                        "notes": notes,
                        "status": "Completed",
                        "picture_before": before_file_objects,
                        "picture_after": after_file_objects
                    }

                    if update_baserow_row(JOB_DETAILS_TABLE_ID, f_id, up_payload) in [200, 204]:
                        # ✅ Patch local list so sync sees the updated status immediately
                        for item in all_details:
                            if str(item['id']) == f_id:
                                item['status'] = 'Completed'  # plain string — matches get_status_value()
                                break
                        sync_work_order_status(order_id, all_details)
                        st.cache_data.clear()
                        st.rerun()
            else:
                st.button(f"Finished {f_name}", key=f"btn_{f_id}_done", type="primary", disabled=True)

        st.markdown('</div>', unsafe_allow_html=True)

# --- 5. Admin: Create Task Page ---
def show_create_task(w_opts, a_opts):
    st.title("📝 Create New Work Order")
    with st.container():
        st.markdown('<div class="main-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 2, 3])
        worker_sel = c1.selectbox("Assign Worker", options=list(w_opts.keys()))
        ex_date = c2.date_input("Execution Date", datetime.now())
        m_notes = c3.text_input("Manager General Notes")
        st.markdown('</div>', unsafe_allow_html=True)

    if 'rows' not in st.session_state:
        st.session_state.rows = [{'apartment': list(a_opts.keys())[0] if a_opts else None, 'start': '09:00', 'end': '11:00', 'notes': ''}]
    if 'order_saved' not in st.session_state:
        st.session_state.order_saved = False

    st.subheader("🏠 Flat Details")
    for i, row in enumerate(st.session_state.rows):
        r1, r2, r3, r4, r5 = st.columns([3, 2, 2, 4, 1])
        st.session_state.rows[i]['apartment'] = r1.selectbox(f"Apt {i}", options=list(a_opts.keys()), key=f"apt_{i}")
        st.session_state.rows[i]['start'] = r2.text_input(f"Start {i}", value=row['start'], key=f"st_{i}")
        st.session_state.rows[i]['end'] = r3.text_input(f"End {i}", value=row['end'], key=f"en_{i}")
        st.session_state.rows[i]['notes'] = r4.text_input(f"Notes {i}", value=row['notes'], key=f"nt_{i}")
        with r5:
            st.write("‎")  # vertical spacer to align button with inputs
            if len(st.session_state.rows) > 1:
                if st.button("🗑️", key=f"del_{i}", help="Remove this flat"):
                    st.session_state.rows.pop(i)
                    st.rerun()

    if st.button("➕ Add Another Flat"):
        st.session_state.rows.append({'apartment': list(a_opts.keys())[0], 'start': '09:00', 'end': '11:00', 'notes': ''})
        st.session_state.order_saved = False
        st.rerun()

    if st.button("🚀 Save and Generate Links", type="primary", use_container_width=True, disabled=st.session_state.order_saved):
        main_p = {
            "employee": [w_opts[worker_sel]],
            "date": ex_date.strftime("%Y-%m-%d"),
            "notes": m_notes,
            "created_by": st.session_state.user,
            "status": "In Progress"
        }
        main_resp = create_baserow_row(WORK_ORDERS_TABLE_ID, main_p)
        if 'id' in main_resp:
            order_id = main_resp['id']
            order_display_id = main_resp.get('sub_id', f"CWO-{order_id}")
            worker_url = f"{PUBLIC_URL}/?order_id={order_id}"
            update_baserow_row(WORK_ORDERS_TABLE_ID, order_id, {"worker_interface_url": worker_url})

            # Build apartment lines for the message while creating job detail rows
            apt_lines = []
            for i, r in enumerate(st.session_state.rows):
                generated_sub_id = f"{order_display_id}-{i+1:02d}"
                apt_id = a_opts[r['apartment']]
                apt_details = get_apartment_details(apt_id)

                address          = apt_details.get('address', '—')
                address_url      = apt_details.get('address_url', '')
                access_info      = apt_details.get('access_information', '—')
                row_notes        = r['notes'] if r['notes'] else '—'

                d_p = {
                    "apartment": [apt_id],
                    "expected_start_time": f"{ex_date}T{r['start']}:00Z",
                    "expected_end_time": f"{ex_date}T{r['end']}:00Z",
                    "notes": r['notes'],
                    "cwo": [order_id],
                    "sub_id": generated_sub_id,
                    "sub_id_suffix": f"{i+1:02d}",
                    "status": "In Progress"
                }
                create_baserow_row(JOB_DETAILS_TABLE_ID, d_p)

                # One block per apartment
                apt_lines.append(
                    f"🏠 *{r['apartment']}*\n"
                    f"   📍 Address      : {address}\n"
                    f"   🗺️  Map           : {address_url}\n"
                    f"   🔑 Access Info  : {access_info}\n"
                    f"   🕐 Start Time   : {r['start']}\n"
                    f"   🕑 End Time     : {r['end']}\n"
                    f"   📝 Notes        : {row_notes}"
                )

            apt_block = "\n\n".join(apt_lines)

            # WhatsApp-friendly message (plain text, emojis, no HTML)
            whatsapp_msg = (
                f"Dear {worker_sel},\n\n"
                f"You have a new work order for *{ex_date.strftime('%A, %d %B %Y')}*.\n\n"
                f"{'─' * 35}\n"
                f"{apt_block}\n"
                f"{'─' * 35}\n\n"
                f"🔗 After finishing please check this link for order progress:\n{worker_url}\n\n"
                f"Thank you! 🙏"
            )

            # Email-friendly message (slightly more formal)
            email_subject = f"New Work Order – {ex_date.strftime('%d %B %Y')} – {worker_sel}"
            email_body = (
                f"Dear {worker_sel},\n\n"
                f"Please find below the details of your new work order scheduled for "
                f"{ex_date.strftime('%A, %d %B %Y')}:\n\n"
                f"{'=' * 40}\n"
                f"{apt_block}\n"
                f"{'=' * 40}\n\n"
                f"After finishing please check this link for order progress:\n{worker_url}\n\n"
                f"Best regards,\nEcoNest Management"
            )

            # ✅ Lock the button FIRST and store results in session state, then rerun
            # so the button re-renders as disabled before the user can click again.
            st.session_state.order_saved = True
            st.session_state.last_result = {
                "worker_url": worker_url,
                "whatsapp_msg": whatsapp_msg,
                "email_subject": email_subject,
                "email_body": email_body,
            }
            st.session_state.rows = [{'apartment': list(a_opts.keys())[0], 'start': '09:00', 'end': '11:00', 'notes': ''}]
            st.rerun()

    # ✅ Show saved results (persisted across reruns via session state)
    if st.session_state.order_saved and 'last_result' in st.session_state:
        res = st.session_state.last_result
        st.success("✅ Order Saved!")
        st.markdown("**🔗 Worker Link:**")
        st.code(res["worker_url"])
        st.divider()
        st.markdown("### 📨 Notification Message")
        tab_wa, tab_email = st.tabs(["💬 WhatsApp", "📧 Email"])
        with tab_wa:
            st.caption("Copy and paste into WhatsApp:")
            st.text_area("WhatsApp Message", value=res["whatsapp_msg"], height=350, key="wa_msg")
        with tab_email:
            st.caption("Copy and paste into your email client:")
            st.text_input("Subject", value=res["email_subject"], key="email_subj")
            st.text_area("Email Body", value=res["email_body"], height=350, key="email_body")

        st.divider()
        if st.button("➕ Create New Task", type="primary", use_container_width=True):
            st.session_state.order_saved = False
            st.session_state.last_result = None
            st.session_state.rows = [{'apartment': list(a_opts.keys())[0] if a_opts else None, 'start': '09:00', 'end': '11:00', 'notes': ''}]
            st.rerun()

# --- 6. Admin: Monitor Page ---
def show_monitor_tasks():
    st.title("🔍 Monitor Work Orders")

    df_o = pd.DataFrame(get_baserow_rows(WORK_ORDERS_TABLE_ID))
    df_d = pd.DataFrame(get_baserow_rows(JOB_DETAILS_TABLE_ID))
    if df_o.empty:
        st.info("No data."); return

    # --- Normalise columns ---
    df_o['worker'] = df_o['employee'].apply(lambda x: x[0]['value'] if x else "N/A")
    df_o['date'] = pd.to_datetime(df_o['date'], errors='coerce').dt.date

    df_d['apt_name'] = df_d['apartment'].apply(lambda x: x[0]['value'] if x else "N/A")
    # ✅ Fix 3a: extract plain string from status dict or string
    df_d['apt_status'] = df_d['status'].apply(get_status_value)
    df_d['p_id'] = df_d['cwo'].apply(lambda x: x[0]['id'] if x else None)

    # --- Filters Row 1: Worker + Date Range ---
    st.subheader("🔎 Filters")
    c1, c2, c3 = st.columns([2, 2, 2])

    f_w = c1.selectbox("Filter by Worker", ["All"] + sorted(df_o['worker'].unique().tolist()))

    valid_dates = df_o['date'].dropna()
    min_date = valid_dates.min() if not valid_dates.empty else datetime.now().date()
    max_date = valid_dates.max() if not valid_dates.empty else datetime.now().date()
    # ✅ Fix 2: date range picker instead of fixed date dropdown
    date_range = c2.date_input(
        "Filter by Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    # ✅ Fix 1: apartment filter sourced from job details
    all_apts = sorted(df_d['apt_name'].dropna().unique().tolist())
    f_apt = c3.selectbox("Filter by Apartment", ["All"] + all_apts)

    # --- Filter Row 2: Apartment Status ---
    # ✅ Fix 1: status filter from apartment-level (job details), not work order
    all_apt_statuses = sorted(df_d['apt_status'].dropna().unique().tolist())
    f_status = st.selectbox("Filter by Apartment Status", ["All"] + all_apt_statuses)

    st.divider()

    # --- Apply work-order level filters ---
    fil = df_o.copy()
    if f_w != "All":
        fil = fil[fil['worker'] == f_w]
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_d, end_d = date_range
        fil = fil[(fil['date'] >= start_d) & (fil['date'] <= end_d)]

    # --- Apply apartment-level filters to job details ---
    fil_d = df_d.copy()
    if f_apt != "All":
        fil_d = fil_d[fil_d['apt_name'] == f_apt]
    if f_status != "All":
        fil_d = fil_d[fil_d['apt_status'] == f_status]

    # Only show work orders that have matching job detail rows after apt/status filter
    matching_order_ids = fil_d['p_id'].dropna().unique().tolist()
    fil = fil[fil['id'].isin(matching_order_ids)]

    # --- Order selector ---
    order_options = fil['sub_id'].tolist() if not fil.empty else []
    sel_id = st.selectbox("Select Order to Drill Down", order_options if order_options else ["— No matching orders —"])

    if sel_id and sel_id != "— No matching orders —":
        oid = fil[fil['sub_id'] == sel_id]['id'].values[0]
        detail_rows = fil_d[fil_d['p_id'] == oid].copy()

        if detail_rows.empty:
            st.info("No apartment details found for this order.")
        else:
            # ✅ Fix 3b: build display table with clean columns
            display = pd.DataFrame({
                "Apartment":        detail_rows['apt_name'].values,
                "Status":           detail_rows['apt_status'].values,   # ✅ plain string, not dict
                "Start Time":       detail_rows['actual_start_time'].values,
                # ✅ Fix 3c: add actual end time column
                "End Time":         detail_rows['actual_end_time'].values if 'actual_end_time' in detail_rows.columns else "—",
                "Notes":            detail_rows['notes'].values,
            })
            st.table(display)

# --- 7. Main Controller ---
def main():
    q = st.query_params
    if "order_id" in q:
        show_worker_interface(q["order_id"])
    else:
        if 'logged_in' not in st.session_state:
            st.session_state.logged_in = False
        if not st.session_state.logged_in:
            st.columns([1,2,1])[1].title("🏢 EcoNest Login")
            u = st.columns([1,2,1])[1].text_input("User")
            p = st.columns([1,2,1])[1].text_input("Pass", type="password")
            if st.columns([1,2,1])[1].button("Login"):
                if u in USERS and USERS[u] == p:
                    st.session_state.logged_in = True
                    st.session_state.user = u
                    st.rerun()
        else:
            with st.sidebar:
                st.title("🛠️ EcoNest Admin")
                choice = st.radio("Navigation", ["➕ Create Task", "🔍 Monitor Tasks"])
                st.divider() 
                st.markdown("""
                    <div style='text-align: center; color: gray; font-size: 0.8em;'>
                        Developed by: <br>
                        <strong>Alfa Systems</strong><br>
                        <span style='color: #007bff;'>v1.0.0 Beta</span>
                    </div>
                """, unsafe_allow_html=True)
                st.sidebar.markdown("---") 
                if st.button("Logout"):
                    st.session_state.logged_in = False
                    st.rerun()

            emp_r = get_baserow_rows(EMPLOYEES_TABLE_ID)
            apt_r = get_baserow_rows(APARTMENTS_TABLE_ID)
            w_opts = {e.get('name'): e.get('id') for e in emp_r if 'id' in e}
            a_opts = {a.get('name'): a.get('id') for a in apt_r if 'id' in a}

            # Reset order_saved when user navigates away from Create Task and returns
            if 'last_page' not in st.session_state:
                st.session_state.last_page = choice
            if st.session_state.last_page != choice:
                st.session_state.last_page = choice
                st.session_state.order_saved = False

            if choice == "➕ Create Task":
                show_create_task(w_opts, a_opts)
            else:
                show_monitor_tasks()

if __name__ == "__main__":
    main()