import streamlit as st
import pandas as pd
import math
import sys
from datetime import datetime

# --- Conditional Import for AutoCAD ---
if sys.platform == 'win32':
    from pyautocad import Autocad
try:
    from fpdf import FPDF
except ImportError:
    st.error("FPDF library not found. Please install it using: pip install fpdf2")
    st.stop()


# --- PDF Generation Function (Multi-Page) ---
def create_multipage_pdf(df):
    """Creates a multi-page PDF with the schedule and a separate wastage report."""
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    
    # --- Page 1: Bar Bending Schedule ---
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, 'Bar Bending Schedule', 0, 1, 'C')
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(0, 5, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
    pdf.ln(5)

    # Main table (excluding wastage column)
    df_schedule = df.drop(columns=['Wastage (m)'])
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    col_widths = {'Barmark': 22, 'Grade': 20, 'Location': 45, 'Cut Length (m)': 25, 'Number of Units': 25, 'Stock Length (m)': 25, 'Num Stock Bars': 25, 'Lengths (mm)': 66}
    for col_name in df_schedule.columns:
        width = col_widths.get(col_name, 20)
        pdf.cell(width, 10, col_name, border=1, fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 8)
    for index, row in df_schedule.iterrows():
        for col_name in df_schedule.columns:
            width = col_widths.get(col_name, 20)
            pdf.cell(width, 10, str(row[col_name]), border=1, align='C')
        pdf.ln()

    # --- Page 2: Wastage Analysis Report ---
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, 'Wastage Analysis Report', 0, 1, 'C')
    pdf.ln(5)

    # Wastage Summary
    df_6m_scenario = recalculate_with_fixed_length(df.copy(), 6.0)
    total_wastage_optimal = df['Wastage (m)'].sum()
    total_wastage_6m = pd.to_numeric(df_6m_scenario['Wastage (m)'], errors='coerce').sum()
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(90, 10, 'Total Wastage (Optimal Schedule):', border=1)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 10, f' {total_wastage_optimal:.2f} m', border=1)
    pdf.ln()
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(90, 10, 'Total Wastage (6m-Only Scenario):', border=1)
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 10, f' {total_wastage_6m:.2f} m', border=1)
    pdf.ln()
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(224, 235, 254) # Light blue fill
    pdf.cell(90, 10, 'Material Saved by Optimization:', border=1, fill=True)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 10, f' {total_wastage_6m - total_wastage_optimal:.2f} m', border=1, fill=True)
    pdf.ln(15)

    # Detailed Wastage Table
    df_wastage = df[['Barmark', 'Location', 'Stock Length (m)', 'Wastage (m)']]
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(0, 10, 'Wastage per Bar Mark (Optimal Schedule)', 0, 1, 'L')
    pdf.ln(2)
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    wastage_col_widths = {'Barmark': 40, 'Location': 100, 'Stock Length (m)': 50, 'Wastage (m)': 50}
    for col_name in df_wastage.columns:
        pdf.cell(wastage_col_widths[col_name], 10, col_name, border=1, fill=True, align='C')
    pdf.ln()
    
    pdf.set_font('Helvetica', '', 8)
    for index, row in df_wastage.iterrows():
        for col_name in df_wastage.columns:
            pdf.cell(wastage_col_widths[col_name], 10, str(row[col_name]), border=1, align='C')
        pdf.ln()

    return pdf.output(dest='S').encode('latin-1')


# --- Core Calculation Functions (remain the same) ---
def bars_and_offcuts(cut_length, bar_size, num_cuts_needed):
    if cut_length <= 0: return {"Error": "Cut length must be positive."}
    if cut_length > bar_size: return {"Error": f"Cut length ({cut_length}m) is greater than stock bar size ({bar_size}m)."}
    cuts_per_bar = int(bar_size // cut_length)
    if cuts_per_bar == 0: return {"Error": "Cannot get any cuts from the selected bar size."}
    num_full_bars = num_cuts_needed // cuts_per_bar
    remaining_cuts = num_cuts_needed % cuts_per_bar
    offcuts = []
    offcut_from_full_bar = bar_size - (cuts_per_bar * cut_length)
    for _ in range(num_full_bars):
        offcuts.append(offcut_from_full_bar)
    bars_used = num_full_bars
    if remaining_cuts > 0:
        bars_used += 1
        offcut_from_last_bar = bar_size - (remaining_cuts * cut_length)
        offcuts.append(offcut_from_last_bar)
    total_wastage = sum(offcuts)
    return {"bars_used": bars_used, "offcuts": offcuts, "total_wastage": round(total_wastage, 3)}

def optimal_bar_size(cut_length, num_cuts_needed):
    standard_bar_sizes = [6.0, 7.5, 9.0, 12.0]
    best_option = {'wastage': float('inf')}
    if cut_length > max(standard_bar_sizes):
        result = bars_and_offcuts(cut_length, 12.0, num_cuts_needed)
        return {'optimal_size': 12.0, 'bars_required': result['bars_used'], 'wastage': result['total_wastage']}
    for bar in standard_bar_sizes:
        if bar < cut_length: continue
        result = bars_and_offcuts(cut_length, bar, num_cuts_needed)
        if "Error" not in result and result['total_wastage'] < best_option['wastage']:
            best_option = {'optimal_size': bar, 'bars_required': result['bars_used'], 'wastage': result['total_wastage']}
    return best_option

def bm(Barmark, Lengths, Type, Diameter, bends_90, Unit_number, Location, Preferred_Length):
    CutL_mm = Cutlength(Lengths, Diameter, bends_90)
    CutL_m = round(CutL_mm / 1000, 3)
    wastage = 0
    if Preferred_Length == "Optimal":
        optimal_result = optimal_bar_size(CutL_m, Unit_number)
        if 'optimal_size' not in optimal_result:
            st.error(f"Could not find an optimal bar for cut length {CutL_m}m.")
            return None
        Pref_L, Preferred_Length_used, wastage = optimal_result['optimal_size'], optimal_result['bars_required'], optimal_result['wastage']
    else:
        Pref_L = float(Preferred_Length.replace('m', ''))
        bar_info = bars_and_offcuts(CutL_m, Pref_L, Unit_number)
        if "Error" in bar_info:
            st.error(bar_info["Error"])
            return None
        Preferred_Length_used, wastage = bar_info["bars_used"], bar_info["total_wastage"]
    My_Bar = {"Barmark": [Barmark], "Grade": [f"{Type}{Diameter}"], "Location": [Location], "Cut Length (m)": [CutL_m], "Number of Units": [Unit_number], "Stock Length (m)": [Pref_L], "Num Stock Bars": [Preferred_Length_used], "Wastage (m)": [wastage], "Lengths (mm)": [str(Lengths)]}
    return pd.DataFrame(My_Bar)

def recalculate_with_fixed_length(df, fixed_length=6.0):
    df_copy = df.copy()
    for index, row in df_copy.iterrows():
        cut_length, num_units = row['Cut Length (m)'], row['Number of Units']
        result = bars_and_offcuts(cut_length, fixed_length, num_units)
        if "Error" not in result:
            df_copy.loc[index, ['Stock Length (m)', 'Num Stock Bars', 'Wastage (m)']] = [fixed_length, result['bars_used'], result['total_wastage']]
        else:
            df_copy.loc[index, ['Stock Length (m)', 'Num Stock Bars', 'Wastage (m)']] = [fixed_length, 'N/A', 'N/A']
    return df_copy

def Cutlength(lengths, diameter, number_90_bends):
    sum_lengths = sum(lengths)
    Bend_deductions = {10: 20, 12: 24, 16: 32, 18: 36, 20: 40, 25: 50, 32: 64}
    return sum_lengths - (Bend_deductions.get(diameter, 0) * number_90_bends)

# --- STREAMLIT UI ---
def bbs_generator():
    st.header("Bar Bending Schedule (BBS) Generator")
    with st.expander("Step 1: Add Bar Mark to Schedule", expanded=True):
        with st.form("barmark_form"):
            c1, c2 = st.columns(2)
            with c1:
                barmark, location, unit_number = st.text_input("Bar Mark Label", "BM01"), st.text_input("Location", "Footing 1"), st.number_input("Number of Units", 1, value=10)
            with c2:
                type_rebar, diameter, bends_90 = st.selectbox("Rebar Type", ["D", "HD"], 1), st.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], 1), st.number_input("Number of 90° Bends", 0, value=2)
            lengths_str = st.text_input("Lengths (comma-separated, in mm)", "200,1000,200")
            preferred_length = st.selectbox("Stock Bar Length", ["Optimal", "6m", "7.5m", "9m", "12m"], 0, help="Select 'Optimal' to find the most material-efficient stock length.")
            if st.form_submit_button("➕ Add Bar to Schedule"):
                try:
                    lengths_list = [int(l.strip()) for l in lengths_str.split(',')]
                    new_bar_df = bm(barmark, lengths_list, type_rebar, diameter, bends_90, unit_number, location, preferred_length)
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
            st.subheader("📉 Scenario Analysis")
            if st.button("Compare with 6m-Only Stock"):
                df_6m_scenario = recalculate_with_fixed_length(full_schedule_df, 6.0)
                total_wastage_optimal = full_schedule_df['Wastage (m)'].sum()
                total_wastage_6m = pd.to_numeric(df_6m_scenario['Wastage (m)'], errors='coerce').sum()
                extra_wastage = total_wastage_6m - total_wastage_optimal
                st.write("This analysis compares your optimized schedule against one where all bars are cut from 6m stock lengths.")
                col1, col2, col3 = st.columns(3)
                col1.metric("Wastage with Optimal Lengths", f"{total_wastage_optimal:.2f} m")
                col2.metric("Wastage with 6m Lengths", f"{total_wastage_6m:.2f} m", delta=f"{extra_wastage:.2f} m more waste", delta_color="inverse")
                col3.metric("Optimization Savings", f"{extra_wastage:.2f} m", help="Meters of material saved by using optimal stock lengths instead of only 6m bars.")
                st.write("**Recalculated Schedule (6m Stock Only)**")
                st.dataframe(df_6m_scenario)

def main():
    st.set_page_config(page_title="Rebar Optimization Suite", layout="wide", initial_sidebar_state="expanded")
    st.title("Rebar Optimization Suite 🏗️")
    if 'schedule_df_list' not in st.session_state: st.session_state.schedule_df_list = []
    
    st.sidebar.title("Actions")
    if st.sidebar.button("Clear Current Schedule", use_container_width=True, type="primary"):
        if st.session_state.schedule_df_list:
            st.session_state.show_clear_dialog = True
        else:
            st.toast("Schedule is already empty.")
    
    # --- Dialog for Clear Confirmation ---
    if st.session_state.get('show_clear_dialog', False):
        with st.dialog("Clear Schedule Confirmation",-1):
            st.warning("Are you sure? This will clear the current schedule.")
            full_schedule_df = pd.concat(st.session_state.schedule_df_list, ignore_index=True)
            pdf_bytes = create_multipage_pdf(full_schedule_df)
            
            def clear_state():
                st.session_state.schedule_df_list = []
                st.session_state.show_clear_dialog = False

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(label="📁 Download & Clear", data=pdf_bytes, file_name=f"BBS_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", on_click=clear_state, use_container_width=True)
            with col2:
                if st.button("⚠️ Clear without Downloading", on_click=clear_state, use_container_width=True):
                    pass
    
    st.sidebar.markdown("---")
    st.sidebar.info("This app helps optimize rebar cutting to minimize material wastage.")
    st.sidebar.markdown(f"**Location:** Suva, Fiji\n\n**Date:** {datetime.now().strftime('%d-%b-%Y')}")
    
    bbs_generator()

if __name__ == "__main__":
    main()
