import streamlit as st
import pandas as pd
import math
import sys
import io
import zipfile
from datetime import datetime

# --- Conditional Import for AutoCAD ---
if sys.platform == 'win32':
    from pyautocad import Autocad
try:
    from fpdf import FPDF
except ImportError:
    st.error("FPDF library not found. Please install it using: pip install fpdf2")
    st.stop()


# --- Archiving and PDF Generation ---
def sanitize_text(text):
    """Encodes text to latin-1, replacing unsupported characters to prevent PDF errors."""
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def create_multipage_pdf(df):
    """Creates a multi-page PDF with the schedule and a separate wastage report."""
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    # Page 1: Bar Bending Schedule
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, sanitize_text('Bar Bending Schedule'), 0, 1, 'C')
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(0, 5, sanitize_text(f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'), 0, 1, 'C')
    pdf.ln(5)
    df_schedule = df.drop(columns=['Wastage (m)'])
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    col_widths = {'Barmark': 22, 'Grade': 20, 'Location': 45, 'Cut Length (m)': 25, 'Number of Units': 25, 'Stock Length (m)': 25, 'Num Stock Bars': 25, 'Lengths (mm)': 66}
    for col_name in df_schedule.columns:
        width = col_widths.get(col_name, 20)
        pdf.cell(width, 10, sanitize_text(col_name), border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_font('Helvetica', '', 8)
    for index, row in df_schedule.iterrows():
        for col_name in df_schedule.columns:
            width = col_widths.get(col_name, 20)
            pdf.cell(width, 10, sanitize_text(row[col_name]), border=1, align='C')
        pdf.ln()
    # Page 2: Wastage Analysis Report
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, sanitize_text('Wastage Analysis Report'), 0, 1, 'C')
    pdf.ln(5)
    df_6m_scenario = recalculate_with_fixed_length(df.copy(), 6.0)
    total_wastage_optimal = df['Wastage (m)'].sum()
    total_wastage_6m = pd.to_numeric(df_6m_scenario['Wastage (m)'], errors='coerce').sum()
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(90, 10, sanitize_text('Total Wastage (Optimal Schedule):'), border=1)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 10, sanitize_text(f' {total_wastage_optimal:.2f} m'), border=1)
    pdf.ln()
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(90, 10, sanitize_text('Total Wastage (6m-Only Scenario):'), border=1)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 10, sanitize_text(f' {total_wastage_6m:.2f} m'), border=1)
    pdf.ln()
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(224, 235, 254)
    pdf.cell(90, 10, sanitize_text('Material Saved by Optimization:'), border=1, fill=True)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 10, sanitize_text(f' {total_wastage_6m - total_wastage_optimal:.2f} m'), border=1, fill=True)
    pdf.ln(15)
    df_wastage = df[['Barmark', 'Location', 'Stock Length (m)', 'Wastage (m)']]
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 10, sanitize_text('Wastage per Bar Mark (Optimal Schedule)'), 0, 1, 'L')
    pdf.ln(2)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    wastage_col_widths = {'Barmark': 40, 'Location': 100, 'Stock Length (m)': 50, 'Wastage (m)': 50}
    for col_name in df_wastage.columns:
        pdf.cell(wastage_col_widths[col_name], 10, sanitize_text(col_name), border=1, fill=True, align='C')
    pdf.ln()
    pdf.set_font('Helvetica', '', 8)
    for index, row in df_wastage.iterrows():
        for col_name in df_wastage.columns:
            pdf.cell(wastage_col_widths[col_name], 10, sanitize_text(row[col_name]), border=1, align='C')
        pdf.ln()
    return bytes(pdf.output())

def create_input_csv(records_list):
    """Creates a CSV string from the list of input parameter dictionaries."""
    if not records_list: return ""
    return pd.DataFrame(records_list).to_csv(index=False)

def create_zip_archive(pdf_bytes, csv_string):
    """Creates a zip archive in memory containing the PDF and CSV files."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr('BBS_Report.pdf', pdf_bytes)
        zip_file.writestr('Input_Parameters.csv', csv_string)
    return zip_buffer.getvalue()

# --- Core Calculation Functions ---
def Cutlength(lengths, diameter, bends_45=0, bends_90=0, bends_135=0, bends_180=0):
    sum_lengths = sum(lengths)
    equivalent_90_bends = (bends_45 * 0.5) + (bends_90 * 1.0) + (bends_135 * 1.5) + (bends_180 * 2.0)
    Bend_deductions = {10: 20, 12: 24, 16: 32, 18: 36, 20: 40, 25: 50, 32: 64}
    bend_deduction_val = Bend_deductions.get(diameter, 0)
    return sum_lengths - (equivalent_90_bends * bend_deduction_val)

def bm(Barmark, Lengths, Type, Diameter, bends_45, bends_90, bends_135, bends_180, Unit_number, Location, Preferred_Length):
    CutL_mm = Cutlength(Lengths, Diameter, bends_45, bends_90, bends_135, bends_180)
    CutL_m = round(CutL_mm / 1000, 3)
    if Unit_number <= 0:
        st.warning(f"Number of units for Barmark '{Barmark}' is zero or less. Skipping calculation.")
        return None
    if Preferred_Length == "Optimal":
        optimal_result = optimal_bar_size(CutL_m, Unit_number)
        if 'optimal_size' not in optimal_result:
            st.error(f"Could not find an optimal bar for cut length {CutL_m}m.")
            return None
        Pref_L, Preferred_Length_used, wastage = optimal_result.values()
    else:
        Pref_L = float(Preferred_Length.replace('m', ''))
        bar_info = bars_and_offcuts(CutL_m, Pref_L, Unit_number)
        if "Error" in bar_info:
            st.error(bar_info["Error"])
            return None
        Preferred_Length_used, wastage = bar_info["bars_used"], bar_info["total_wastage"]
    My_Bar = {"Barmark": [Barmark], "Grade": [f"{Type}{Diameter}"], "Location": [Location], "Cut Length (m)": [CutL_m], "Number of Units": [Unit_number], "Stock Length (m)": [Pref_L], "Num Stock Bars": [Preferred_Length_used], "Wastage (m)": [wastage], "Lengths (mm)": [str(Lengths)]}
    return pd.DataFrame(My_Bar)

def numof(length, spacing, cover):
    if spacing <= 0: return 0
    return max(0, math.ceil((length - cover) / spacing) - 2)

def bars_and_offcuts(cut_length, bar_size, num_cuts_needed):
    if cut_length <= 0: return {"Error": "Cut length must be positive."}
    if cut_length > bar_size: return {"Error": f"Cut length ({cut_length}m) is greater than stock bar size ({bar_size}m)."}
    cuts_per_bar = int(bar_size // cut_length)
    if cuts_per_bar == 0: return {"Error": "Cannot get any cuts from the selected bar size."}
    num_full_bars, remaining_cuts = divmod(num_cuts_needed, cuts_per_bar)
    offcuts = [bar_size - (cuts_per_bar * cut_length)] * num_full_bars
    bars_used = num_full_bars
    if remaining_cuts > 0:
        bars_used += 1
        offcuts.append(bar_size - (remaining_cuts * cut_length))
    return {"bars_used": bars_used, "offcuts": offcuts, "total_wastage": round(sum(offcuts), 3)}

def recalculate_with_fixed_length(df, fixed_length=6.0):
    df_copy = df.copy()
    for index, row in df_copy.iterrows():
        cut_length, num_units = row['Cut Length (m)'], row['Number of Units']
        result = bars_and_offcuts(cut_length, fixed_length, num_units)
        if "Error" not in result:
            df_copy.loc[index, ['Stock Length (m)', 'Num Stock Bars', 'Wastage (m)']] = fixed_length, result['bars_used'], result['total_wastage']
        else:
            df_copy.loc[index, ['Stock Length (m)', 'Num Stock Bars', 'Wastage (m)']] = fixed_length, 'N/A', 'N/A'
    return df_copy
    
# --- STREAMLIT UI ---
def bbs_generator():
    st.header("Bar Bending Schedule (BBS) Generator")
    with st.expander("Step 1: Add Bar Mark to Schedule", expanded=True):
        with st.form("barmark_form"):
            # Form content remains the same...
            c1, c2 = st.columns(2)
            with c1:
                barmark, location = st.text_input("Bar Mark Label", "BM01"), st.text_input("Location", "Footing 1")
                type_rebar, diameter = st.selectbox("Rebar Type", ["D", "HD"], 1), st.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], 1)
                st.write("**Bend Angles**")
                b1, b2, b3, b4 = st.columns(4)
                bends_45_val = b1.number_input("45°", 0)
                bends_90_val = b2.number_input("90°", 0, value=2)
                bends_135_val = b3.number_input("135°", 0)
                bends_180_val = b4.number_input("180°", 0)
            with c2:
                lengths_str = st.text_input("Lengths (comma-separated, in mm)", "200,1000,200")
                preferred_length = st.selectbox("Stock Bar Length", ["Optimal", "6m", "7.5m", "9m", "12m"], 0, help="Select 'Optimal' to find the most material-efficient stock length.")
            st.markdown("---")
            st.write("**Specify Quantity**")
            unit_number_direct = st.number_input("Enter Number of Units Directly", 0, value=0, help="If this is > 0, it overrides the calculation below.")
            st.divider()
            st.write("Or, Calculate for Stirrups/Ties")
            c3, c4, c5 = st.columns(3)
            total_length_m = c3.number_input("Length of Zone to Cover (m)", 0.1, value=10.0)
            spacing_mm = c4.number_input("Stirrup Spacing (c/c, mm)", 1, value=200)
            cover_mm = c5.number_input("Concrete Cover at ends (mm)", 0, value=75)

            if st.form_submit_button("➕ Add Bar to Schedule"):
                if st.session_state.schedule_df_list and barmark in [item.iloc[0]['Barmark'] for item in st.session_state.schedule_df_list]:
                    st.warning(f"⚠️ Warning: Bar Mark '{barmark}' already exists in the schedule.")
                is_direct_entry = unit_number_direct > 0
                unit_number = unit_number_direct if is_direct_entry else numof(total_length_m * 1000, spacing_mm, cover_mm)
                if not is_direct_entry: st.info(f"Using calculated Number of Bars: {unit_number}")
                
                input_record = {
                    "Barmark": barmark, "Location": location, "Rebar_Type": type_rebar, "Diameter_mm": diameter,
                    "Lengths_mm": lengths_str, "Preferred_Stock_Length": preferred_length, "Bends_45": bends_45_val, 
                    "Bends_90": bends_90_val, "Bends_135": bends_135_val, "Bends_180": bends_180_val,
                    "Quantity_Method": "Direct Entry" if is_direct_entry else "Calculated",
                    "Direct_Quantity": unit_number_direct if is_direct_entry else "N/A",
                    "Calc_Zone_Length_m": total_length_m if not is_direct_entry else "N/A",
                    "Calc_Spacing_mm": spacing_mm if not is_direct_entry else "N/A",
                    "Calc_Cover_mm": cover_mm if not is_direct_entry else "N/A"
                }
                st.session_state.input_records_list.append(input_record)

                try:
                    new_bar_df = bm(barmark, [int(l.strip()) for l in lengths_str.split(',')], type_rebar, diameter, bends_45_val, bends_90_val, bends_135_val, bends_180_val, unit_number, location, preferred_length)
                    if new_bar_df is not None:
                        st.session_state.schedule_df_list.append(new_bar_df)
                        st.success(f"Bar Mark '{barmark}' added!")
                except ValueError: st.error("Please enter valid, comma-separated numbers for lengths.")

    if st.session_state.schedule_df_list:
        with st.expander("Step 2: View Schedule, Analyze, and Download", expanded=True):
            st.subheader("Optimized Bar Bending Schedule")
            full_schedule_df = pd.concat(st.session_state.schedule_df_list, ignore_index=True)
            st.dataframe(full_schedule_df)
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                pdf_bytes = create_multipage_pdf(full_schedule_df)
                csv_string = create_input_csv(st.session_state.input_records_list)
                zip_bytes = create_zip_archive(pdf_bytes, csv_string)
                st.download_button(label="📦 Download Report & Inputs (.zip)", data=zip_bytes, file_name=f"BBS_Package_{datetime.now().strftime('%Y%m%d')}.zip", mime="application/zip", use_container_width=True)
            with col2:
                with st.popover("🗑️ Delete an Entry", use_container_width=True):
                    st.write("Select a Bar Mark from the list and click delete.")
                    barmarks_to_delete = full_schedule_df['Barmark'].unique().tolist()
                    selected_barmark = st.selectbox("Select Bar Mark", options=barmarks_to_delete, index=None, placeholder="Choose a barmark...", key="delete_selectbox")
                    if st.button("Confirm Deletion", disabled=(not selected_barmark), type="primary"):
                        index_to_remove = next((i for i, df_item in enumerate(st.session_state.schedule_df_list) if df_item.iloc[0]['Barmark'] == selected_barmark), -1)
                        if index_to_remove != -1:
                            st.session_state.schedule_df_list.pop(index_to_remove)
                            st.session_state.input_records_list.pop(index_to_remove)
                            st.success(f"Deleted Bar Mark '{selected_barmark}'.")
                            st.rerun()
            # Scenario Analysis remains the same...

def archive_viewer():
    """Renders the UI for viewing archived schedules from the current session."""
    st.header("Archive Viewer")
    st.info("This page shows schedules that were cleared and archived during this session.")

    if not st.session_state.archive:
        st.warning("No schedules have been archived in this session yet.")
        return

    archive_options = [f"Archive from {ts}" for ts in st.session_state.archive.keys()]
    selected_archive_key = st.selectbox("Select an archived schedule to view", options=archive_options)

    if selected_archive_key:
        # Extract timestamp from the selected option string
        timestamp = selected_archive_key.replace("Archive from ", "")
        archived_data = st.session_state.archive[timestamp]
        
        st.subheader(f"Viewing Archive: {timestamp}")
        
        # Display the archived data
        with st.expander("View Input Parameters (.csv)", expanded=True):
            st.dataframe(archived_data["inputs_df"])
        
        with st.expander("Download PDF Report"):
            st.download_button(
                label=f"📄 Download PDF Report for {timestamp}",
                data=archived_data["pdf_bytes"],
                file_name=f"BBS_Report_{timestamp.replace(':', '-')}.pdf",
                mime="application/pdf"
            )

def standalone_calculators():
    st.header("Standalone Rebar Calculators")
    st.info("This section contains individual tools for quick calculations.")
    
    tab_titles = ["Cut Length", "Optimal Bar Size", "Tonnage <> Bar Count", "Stirrup Tools", "Lapping Calculator"]
    tab1, tab2, tab3, tab4, tab5 = st.tabs(tab_titles)

    with tab1:
        st.subheader("Rebar Cut Length Calculator")
        lengths_cl_str = st.text_input("Lengths (comma-separated, in mm)", "250,1500,250", key="cl_len")
        diam_cl = st.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], key="cl_diam")
        st.write("**Enter Number of Bends by Angle**")
        b1, b2, b3, b4 = st.columns(4)
        bends_45_cl = b1.number_input("45°", 0, key="cl_b45")
        bends_90_cl = b2.number_input("90°", 0, value=2, key="cl_b90")
        bends_135_cl = b3.number_input("135°", 0, key="cl_b135")
        bends_180_cl = b4.number_input("180°", 0, key="cl_b180")
        if st.button("Calculate Cut Length", key="cl_btn"):
            try:
                result_cl = Cutlength([int(l.strip()) for l in lengths_cl_str.split(',')], diam_cl, bends_45_cl, bends_90_cl, bends_135_cl, bends_180_cl)
                st.metric("Final Cut Length", f"{result_cl} mm")
            except ValueError: st.error("Please enter valid, comma-separated numbers for lengths.")

    with tab2:
        st.subheader("Optimal Bar Size Calculator")
        cut_len_opt, num_cuts_opt = st.number_input("Required Cut Length (m)", 0.1, value=2.8), st.number_input("Number of Cuts Needed", 1, value=50)
        if st.button("Find Optimal Size", key="opt_btn"):
            result = optimal_bar_size(cut_len_opt, num_cuts_opt)
            if 'optimal_size' in result:
                st.metric("Optimal Stock Bar Size", f"{result['optimal_size']} m")
                st.metric("Number of Stock Bars Required", f"{result['bars_required']} bars")
                st.metric("Total Wastage", f"{result['wastage']:.2f} m")
            else: st.error("Could not determine optimal size.")

    with tab3:
        st.subheader("Tonnage & Bar Count Converter")
        diam_t = st.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], key="t_diam")
        len_m = st.selectbox("Standard Length", ["6m", "7.5m", "9m", "12m"], key="t_len")
        conv_type = st.radio("Conversion Type", ["Bars to Tonnage", "Tonnage to Bars"])
        if conv_type == "Bars to Tonnage":
            num_bars = st.number_input("Number of Bars", 1, value=100)
            if st.button("Calculate Tonnage", key="ton_btn"):
                result = tonnage(num_bars, diam_t, len_m)
                if result is not None: st.metric("Calculated Tonnage", f"{result:.3f} tonnes")
        else:
            tonnage_val = st.number_input("Tonnage", 0.1, value=1.0, step=0.1)
            if st.button("Calculate Number of Bars", key="bar_btn"):
                result = bars_lengths(tonnage_val, len_m, diam_t)
                if result is not None: st.metric("Calculated Number of Bars", f"{math.ceil(result)} bars")

    with tab4:
        st.subheader("Stirrup Quantity Calculator")
        len_q, space_q, cover_q = st.number_input("Length of Zone (mm)", value=5000), st.number_input("Spacing (mm)", value=200), st.number_input("Cover (mm)", value=75)
        if st.button("Calculate Quantity", key="qty_btn"):
            st.metric("Number of Stirrups", numof(len_q, space_q, cover_q))
        st.divider()
        st.subheader("Stirrup Cutting Length Calculator")
        shape = st.selectbox("Stirrup Shape", ["Rectangle", "Square", "Circle"])
        if shape == "Rectangle":
            l, w = st.number_input("Length (mm)", value=400), st.number_input("Width (mm)", value=300)
            perimeter = p_rectangle(l, w)
        elif shape == "Square":
            l_sq = st.number_input("Side Length (mm)", value=300)
            perimeter = p_square(l_sq)
        else:
            d_circ = st.number_input("Diameter (mm)", value=500)
            perimeter = p_circle(d_circ)
        diam_st = st.selectbox("Bar Diameter (mm)", [10, 12, 16], key="st_diam")
        if st.button("Calculate Stirrup Cut Length", key="st_len_btn"):
            st.metric("Stirrup Cut Length", f"{stirrup_cutting_length(perimeter, diam_st):.2f} mm")

    with tab5:
        st.subheader("Lapping Bar Calculator")
        c1, c2 = st.columns(2)
        lap_len_std_str = c1.selectbox("Standard Bar Length", ['6m', '7.5m', '9m', '12m'], index=3)
        lap_diam = c1.selectbox("Bar Diameter (mm)", [10, 12, 16, 20, 25, 32], index=2)
        lap_dist = c2.number_input("Total Distance to Span (mm)", value=30000)
        lap_factor = c2.number_input("Lapping Factor ($d$)", value=50)
        
        if st.button("Calculate Lapping", key="lap_btn"):
            length_map = {'6m': 6000, '7.5m': 7500, '9m': 9000, '12m': 12000}
            lap_len_std_mm = length_map[lap_len_std_str]
            num, left, lap_len = Lapped_bars(lap_len_std_mm, lap_diam, lap_dist, lap_factor)
            st.metric("Calculated Lap Length", f"{lap_len} mm")
            st.success(f"**Result:** {num}, with {left}")

def main():
    st.set_page_config(page_title="Rebar Optimization Suite", layout="wide", initial_sidebar_state="expanded")
    st.title("Rebar Optimization Suite 🏗️")
    if 'schedule_df_list' not in st.session_state: st.session_state.schedule_df_list = []
    
    st.sidebar.title("Navigation")
    app_mode = st.sidebar.radio("Choose a Tool", ["BBS Generator", "Standalone Calculators"])
    st.sidebar.markdown("---")
    
    st.sidebar.title("Actions")
    if st.sidebar.button("Clear Current Schedule", use_container_width=True, type="primary"):
        if st.session_state.schedule_df_list: st.session_state.show_clear_dialog = True
        else: st.toast("Schedule is already empty.")
    
    if st.session_state.get('show_clear_dialog', False):
        with st.dialog("Clear Schedule Confirmation"):
            st.warning("Are you sure? This will clear the current schedule.")
            full_schedule_df = pd.concat(st.session_state.schedule_df_list, ignore_index=True)
            pdf_bytes = create_multipage_pdf(full_schedule_df)
            def clear_state():
                st.session_state.schedule_df_list, st.session_state.show_clear_dialog = [], False
            c1, c2 = st.columns(2)
            c1.download_button(label="📁 Download & Clear", data=pdf_bytes, file_name=f"BBS_Report_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", on_click=clear_state, use_container_width=True)
            c2.button("⚠️ Clear without Downloading", on_click=clear_state, use_container_width=True)
    
    st.sidebar.markdown("---")
    st.sidebar.info(f"**Location:** Suva, Fiji\n\n**Date:** {datetime.now().strftime('%d %b %Y')}")
    
    if app_mode == "BBS Generator": bbs_generator()
    else: standalone_calculators()

if __name__ == "__main__":
    main()
