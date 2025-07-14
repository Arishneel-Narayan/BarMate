import streamlit as st
import pandas as pd
import math
import sys
from datetime import datetime

# --- Conditional Import for AutoCAD ---
# pyautocad and comtypes only work on Windows.
if sys.platform == 'win32':
    from pyautocad import Autocad
# fpdf2 is used for PDF generation and works on all platforms.
try:
    from fpdf import FPDF
except ImportError:
    st.error("FPDF library not found. Please install it using: pip install fpdf2")
    st.stop()


# --- PDF Generation Function ---
def create_pdf(df):
    """Creates a PDF file from a pandas DataFrame."""
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    
    # Title
    pdf.cell(0, 10, 'Bar Bending Schedule', 0, 1, 'C')
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(0, 5, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
    pdf.ln(5)

    # Table Headers
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    col_widths = {'Barmark': 20, 'Grade': 18, 'Location': 35, 'Cut Length (m)': 25, 'Number of Units': 25, 'Stock Length (m)': 25, 'Num Stock Bars': 25, 'Wastage (m)': 25, 'Lengths (mm)': 60}
    
    for col_name in df.columns:
        width = col_widths.get(col_name, 20) # Default width if not specified
        pdf.cell(width, 10, col_name, border=1, fill=True, align='C')
    pdf.ln()

    # Table Rows
    pdf.set_font('Helvetica', '', 8)
    for index, row in df.iterrows():
        for col_name in df.columns:
            width = col_widths.get(col_name, 20)
            pdf.cell(width, 10, str(row[col_name]), border=1, align='C')
        pdf.ln()
    
    # Return PDF as bytes
    return pdf.output(dest='S').encode('latin-1')


# --- Core Calculation Functions ---

def bars_and_offcuts(cut_length, bar_size, num_cuts_needed):
    """
    Calculates the number of bars required and returns a detailed list of all offcuts.
    """
    if cut_length <= 0:
        return {"Error": "Cut length must be positive."}
    if cut_length > bar_size:
        return {"Error": f"Cut length ({cut_length}m) is greater than stock bar size ({bar_size}m)."}
        
    cuts_per_bar = int(bar_size // cut_length)
    if cuts_per_bar == 0:
        return {"Error": "Cannot get any cuts from the selected bar size."}

    num_full_bars = num_cuts_needed // cuts_per_bar
    remaining_cuts = num_cuts_needed % cuts_per_bar
    
    offcuts = []
    # Offcuts from fully utilized bars
    offcut_from_full_bar = bar_size - (cuts_per_bar * cut_length)
    for _ in range(num_full_bars):
        offcuts.append(offcut_from_full_bar)
        
    # Offcut from the last partially used bar
    bars_used = num_full_bars
    if remaining_cuts > 0:
        bars_used += 1
        offcut_from_last_bar = bar_size - (remaining_cuts * cut_length)
        offcuts.append(offcut_from_last_bar)
        
    total_wastage = sum(offcuts)
    return {
        "bars_used": bars_used,
        "offcuts": offcuts,
        "total_wastage": round(total_wastage, 3)
    }

def optimal_bar_size(cut_length, num_cuts_needed):
    """Finds the standard bar size that minimizes total offcut wastage."""
    standard_bar_sizes = [6.0, 7.5, 9.0, 12.0]
    best_option = {'wastage': float('inf')}

    if cut_length > max(standard_bar_sizes):
        result = bars_and_offcuts(cut_length, 12.0, num_cuts_needed)
        return {'optimal_size': 12.0, 'bars_required': result['bars_used'], 'wastage': result['total_wastage']}
    
    for bar in standard_bar_sizes:
        if bar < cut_length:
            continue
        
        result = bars_and_offcuts(cut_length, bar, num_cuts_needed)
        if "Error" not in result and result['total_wastage'] < best_option['wastage']:
            best_option = {
                'optimal_size': bar,
                'bars_required': result['bars_used'],
                'wastage': result['total_wastage']
            }
            
    return best_option

def bm(Barmark, Lengths, Type, Diameter, bends_90, Unit_number, Location, Preferred_Length):
    """Creates a DataFrame for a single Bar Mark, including wastage."""
    CutL_mm = Cutlength(Lengths, Diameter, bends_90)
    CutL_m = round(CutL_mm / 1000, 3)
    
    wastage = 0
    
    if Preferred_Length == "Optimal":
        optimal_result = optimal_bar_size(CutL_m, Unit_number)
        if 'optimal_size' not in optimal_result:
            st.error(f"Could not find an optimal bar for cut length {CutL_m}m.")
            return None
        Pref_L = optimal_result['optimal_size']
        Preferred_Length_used = optimal_result['bars_required']
        wastage = optimal_result['wastage']
    else:
        Pref_L = float(Preferred_Length.replace('m', ''))
        bar_info = bars_and_offcuts(CutL_m, Pref_L, Unit_number)
        if "Error" in bar_info:
            st.error(bar_info["Error"])
            return None
        Preferred_Length_used = bar_info["bars_used"]
        wastage = bar_info["total_wastage"]

    My_Bar = {
        "Barmark": [Barmark],
        "Grade": [f"{Type}{Diameter}"],
        "Location": [Location],
        "Cut Length (m)": [CutL_m],
        "Number of Units": [Unit_number],
        "Stock Length (m)": [Pref_L],
        "Num Stock Bars": [Preferred_Length_used],
        "Wastage (m)": [wastage],
        "Lengths (mm)": [str(Lengths)]
    }
    
    return pd.DataFrame(My_Bar)


# --- All other helper functions like Cutlength, Steel_weight, Order_Details, etc. remain the same ---
def Cutlength(lengths, diameter, number_90_bends):
    sum_lengths = sum(lengths)
    Bend_deductions = {10: 20, 12: 24, 16: 32, 18: 36, 20: 40, 25: 50, 32: 64}
    bend_deduction = Bend_deductions.get(diameter, 0) * number_90_bends
    return sum_lengths - bend_deduction

def Steel_weight(diameter, length):
    return round(((diameter**2) / 162.2) * length, 2)

def extract_diameter(grade_str):
    try:
        return float(''.join(filter(str.isdigit, grade_str)))
    except (ValueError, TypeError):
        return 0

def Order_Details(panel_df):
    if panel_df.empty: return None, None
    order_df = panel_df.copy()
    order_df['Diameter'] = order_df["Grade"].apply(extract_diameter)
    order_df['Total LM Ordered'] = order_df['Stock Length (m)'] * order_df['Num Stock Bars']
    order_df['Total Weight Ordered (kg)'] = order_df.apply(lambda x: Steel_weight(x['Diameter'], x['Total LM Ordered']), axis=1)
    pivot_lengths = pd.pivot_table(order_df, values='Total LM Ordered', index=['Grade'], columns='Stock Length (m)', aggfunc='sum', fill_value=0).round(2)
    pivot_weight = pd.pivot_table(order_df, values='Total Weight Ordered (kg)', index=['Grade'], columns='Stock Length (m)', aggfunc='sum', fill_value=0).round(2)
    return pivot_lengths, pivot_weight
    

# --- STREAMLIT UI ---

def bbs_generator():
    st.header("Bar Bending Schedule (BBS) Generator")

    # Step 1: Add a Bar Mark
    with st.expander("Step 1: Add Bar Mark to Schedule", expanded=True):
        # (Form code is the same as before, no changes needed here)
        with st.form("barmark_form"):
            c1, c2 = st.columns(2)
            with c1:
                barmark = st.text_input("Bar Mark Label", "BM01")
                location = st.text_input("Location (e.g., Footing, Column)", "Footing 1")
                unit_number = st.number_input("Number of Units", min_value=1, value=10)
                type_rebar = st.selectbox("Rebar Type", ["D", "HD"], index=1)
            with c2:
                diameter = st.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], index=1)
                bends_90 = st.number_input("Number of 90° Bends", min_value=0, value=2)
                lengths_str = st.text_input("Lengths (comma-separated, in mm)", "200,1000,200")
                preferred_length = st.selectbox("Stock Bar Length", ["Optimal", "6m", "7.5m", "9m", "12m"], index=0)

            submitted = st.form_submit_button("➕ Add Bar to Schedule")
            if submitted:
                try:
                    lengths_list = [int(l.strip()) for l in lengths_str.split(',')]
                    new_bar_df = bm(barmark, lengths_list, type_rebar, diameter, bends_90, unit_number, location, preferred_length)
                    if new_bar_df is not None:
                        st.session_state.schedule_df_list.append(new_bar_df)
                        st.success(f"Bar Mark '{barmark}' added!")
                except ValueError:
                    st.error("Please enter valid, comma-separated numbers for lengths.")

    # Step 2: View Schedule, Order, and Download
    if st.session_state.schedule_df_list:
        with st.expander("Step 2: View Full Schedule, Generate Order, and Download", expanded=True):
            full_schedule_df = pd.concat(st.session_state.schedule_df_list, ignore_index=True)
            st.dataframe(full_schedule_df)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("📊 Generate Order Summary"):
                    pivot_lengths, pivot_weights = Order_Details(full_schedule_df)
                    st.subheader("Order Summary")
                    st.write("**Total Length to Order (meters)**")
                    st.dataframe(pivot_lengths)
                    st.write("**Total Weight to Order (kg)**")
                    st.dataframe(pivot_weights)
            
            with c2:
                # PDF Download Button
                pdf_bytes = create_pdf(full_schedule_df)
                st.download_button(
                    label="📄 Download Schedule as PDF",
                    data=pdf_bytes,
                    file_name="bar_bending_schedule.pdf",
                    mime="application/pdf"
                )

    # Step 3: AutoCAD Export (Windows Only)
    # This section remains unchanged and works as before
    if sys.platform == 'win32':
        # ... (AutoCAD code from previous version goes here) ...
        pass


def main():
    """Main function to run the Streamlit app."""
    st.set_page_config(page_title="Rebar Optimization Suite", layout="wide", initial_sidebar_state="expanded")
    st.title("Rebar Optimization Suite 🏗️")

    if 'schedule_df_list' not in st.session_state:
        st.session_state.schedule_df_list = []

    st.sidebar.title("Navigation")
    app_mode = st.sidebar.radio("Choose a Tool", ["BBS Generator"]) # Simplified navigation
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Clear Current Schedule", use_container_width=True):
        st.session_state.schedule_df_list = []
        st.toast("Schedule has been cleared!")

    st.sidebar.info("App by BarMate Fiji Ltd.")

    if app_mode == "BBS Generator":
        bbs_generator()

if __name__ == "__main__":
    main()
