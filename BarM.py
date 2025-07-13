import streamlit as st
import pandas as pd
import math
import sys

# --- Conditional Import for AutoCAD ---
# pyautocad and comtypes only work on Windows. This check prevents import errors
# when the app is deployed on a Linux-based server (e.g., Streamlit Cloud).
if sys.platform == 'win32':
    from pyautocad import Autocad

# --- Helper & Calculation Functions ---

def tonnage(Number_bars, diameter_mm, Length_m):
    """Calculates the tonnage of rebar based on the number of bars."""
    bar_data = {
        "6m": {10: 270, 12: 188, 16: 106, 20: 68, 25: 43, 32: 26},
        "7.5m": {10: 216, 12: 150, 16: 85, 20: 54, 25: 35, 32: 21},
        "9m": {10: 180, 12: 125, 16: 70, 20: 45, 25: 29, 32: 18},
        "12m": {10: 135, 12: 94, 16: 53, 20: 34, 25: 22, 32: 13}
    }
    if Length_m in bar_data and diameter_mm in bar_data[Length_m]:
        return Number_bars / bar_data[Length_m][diameter_mm]
    return "Invalid length or diameter."

def bars_lengths(tonnage_val, Length_m, diameter):
    """Calculates the number of bars from tonnage."""
    bar_data = {
        "6m": {10: 270, 12: 188, 16: 106, 20: 68, 25: 43, 32: 26},
        "7.5m": {10: 216, 12: 150, 16: 85, 20: 54, 25: 35, 32: 21},
        "9m": {10: 180, 12: 125, 16: 70, 20: 45, 25: 29, 32: 18},
        "12m": {10: 135, 12: 94, 16: 53, 20: 34, 25: 22, 32: 13}
    }
    if Length_m in bar_data and diameter in bar_data[Length_m]:
        return tonnage_val * bar_data[Length_m][diameter]
    return "Invalid length or diameter."


def Cutlength(lengths, diameter, number_90_bends):
    """Calculates the cut length considering bend deductions. All measurements in mm."""
    sum_lengths = sum(lengths)
    Bend_deductions = {10: 20, 12: 24, 16: 32, 18: 36, 20: 40, 25: 50, 32: 64}
    bend_deduction = Bend_deductions.get(diameter, 0) * number_90_bends
    return sum_lengths - bend_deduction

def stirrup_cutting_length(Perimeter, bar_diameter):
    """Calculates the Cutting Length of a stirrup. Assumes 2x135deg hooks & 3x90deg bends."""
    hook_length = 2 * (10 * bar_diameter) # Standard hook length 10d per hook
    bend_deduction = (3 * 2 * bar_diameter) + (2 * 3 * bar_diameter) # 3x90deg + 2x135deg bends
    cutting_length = Perimeter + hook_length - bend_deduction
    return cutting_length

def p_square(length):
    return 4 * length

def p_rectangle(length, width):
    return 2 * (length + width)

def p_circle(diameter):
    return math.pi * diameter

def bars_and_offcuts(cut_length, bar_size, num_cuts_needed):
    """Calculates the number of standard bars required and the resulting offcuts."""
    if cut_length <= 0:
        return {"Error": "Cut length must be positive."}
    if cut_length > bar_size:
        return {"Error": f"Cut length ({cut_length}m) is greater than the stock bar size ({bar_size}m)."}
        
    cuts_per_bar = bar_size // cut_length
    num_bars_needed = math.ceil(num_cuts_needed / cuts_per_bar)
    
    return {"Number of Bars used": num_bars_needed}

def optimal_bar_size(cut_length, num_cuts_needed):
    """Finds the standard bar size that minimizes offcut waste."""
    standard_bar_sizes = [6.0, 7.5, 9.0, 12.0]
    min_offcut_sum = float('inf')
    optimal_size = None
    optimal_bars_required = 0
    
    if cut_length > max(standard_bar_sizes):
        return max(standard_bar_sizes), "Cut length exceeds max standard bar size; using 12m."

    for bar in standard_bar_sizes:
        if bar < cut_length:
            continue
        
        cuts_per_bar = bar // cut_length
        num_bars_needed = math.ceil(num_cuts_needed / cuts_per_bar)
        
        total_length_ordered = num_bars_needed * bar
        total_length_cut = num_cuts_needed * cut_length
        offcut_sum = total_length_ordered - total_length_cut

        if offcut_sum < min_offcut_sum:
            min_offcut_sum = offcut_sum
            optimal_size = bar
            optimal_bars_required = num_bars_needed
            
    return optimal_size, optimal_bars_required

def bm(Barmark, Lengths, Type, Diameter, bends_90, Unit_number, Location, Preferred_Length):
    """Creates a DataFrame for a single Bar Mark."""
    CutL_mm = Cutlength(Lengths, Diameter, bends_90)
    CutL_m = CutL_mm / 1000
    
    if Preferred_Length == "Optimal":
        Pref_L, _ = optimal_bar_size(CutL_m, Unit_number)
        if Pref_L is None:
            st.error(f"Cannot find optimal bar for cut length {CutL_m}m. Please select a manual stock length.")
            return None
    else:
        Pref_L = float(Preferred_Length.replace('m',''))
        
    bar_info = bars_and_offcuts(CutL_m, Pref_L, Unit_number)
    if "Error" in bar_info:
        st.error(bar_info["Error"])
        return None

    Preferred_Length_used = bar_info["Number of Bars used"]
    
    My_Bar = {
        "Barmark": [Barmark],
        "Grade": [f"{Type}{Diameter}"],
        "Location": [Location],
        "Cut Length (m)": [round(CutL_m, 3)],
        "Number of Units": [Unit_number],
        "Stock Length (m)": [Pref_L],
        "Num Stock Bars": [Preferred_Length_used],
        "Lengths (mm)": [str(Lengths)]
    }
    
    return pd.DataFrame(My_Bar)

def Steel_weight(diameter, length):
    """Calculates steel weight in kg."""
    return round(((diameter**2) / 162.2) * length, 2)

def extract_diameter(grade_str):
    """Extracts diameter as a number from a grade string like 'HD12'."""
    try:
        return float(''.join(filter(str.isdigit, grade_str)))
    except (ValueError, TypeError):
        return 0

def Order_Details(panel_df):
    """Generates pivot tables for ordering summary."""
    if panel_df.empty:
        return None, None
        
    order_df = panel_df.copy()
    order_df['Diameter'] = order_df["Grade"].apply(extract_diameter)
    
    order_df['Total LM Cut'] = order_df['Cut Length (m)'] * order_df['Number of Units']
    order_df['Total Weight Used (kg)'] = order_df.apply(lambda x: Steel_weight(x['Diameter'], x['Total LM Cut']), axis=1)

    order_df['Total LM Ordered'] = order_df['Stock Length (m)'] * order_df['Num Stock Bars']
    order_df['Total Weight Ordered (kg)'] = order_df.apply(lambda x: Steel_weight(x['Diameter'], x['Total LM Ordered']), axis=1)

    pivot_lengths = pd.pivot_table(order_df, values='Total LM Ordered', index=['Grade'], columns='Stock Length (m)', aggfunc='sum', fill_value=0).round(2)
    pivot_weight = pd.pivot_table(order_df, values='Total Weight Ordered (kg)', index=['Grade'], columns='Stock Length (m)', aggfunc='sum', fill_value=0).round(2)

    return pivot_lengths, pivot_weight

# --- AutoCAD Integration Functions (Windows Only)---
if sys.platform == 'win32':
    @st.cache_data
    def get_table_info(_acad):
        """Scans AutoCAD for tables and returns their handles and dimensions."""
        table_info = []
        try:
            for entity in _acad.iter_objects('Table'):
                table_info.append(f"Handle: {entity.Handle}, Rows: {entity.Rows}, Cols: {entity.Columns}")
            return table_info
        except Exception as e:
            return [f"Error scanning for tables: {e}"]

    def insert_df_into_table(_acad, table_handle, df, start_row):
        """Inserts a pandas DataFrame into a specified AutoCAD table."""
        try:
            table_obj = _acad.handle_to_object(table_handle)
            col_headers = df.columns.tolist()
            # Insert column headers
            for j, header in enumerate(col_headers):
                if j < table_obj.Columns:
                    table_obj.SetText(start_row - 1, j, str(header))
            # Insert data rows
            for i, row_data in enumerate(df.itertuples(index=False)):
                table_row = start_row + i
                if table_row >= table_obj.Rows:
                    st.warning(f"Table has only {table_obj.Rows} rows. Stopped inserting at row {table_row}.")
                    break
                for j, cell_value in enumerate(row_data):
                    if j < table_obj.Columns:
                        table_obj.SetText(table_row, j, str(cell_value))
            return True, "Data inserted successfully."
        except Exception as e:
            return False, f"Failed to insert data: {e}"

# --- STREAMLIT APP UI ---

def bbs_generator():
    """Main page for creating the Bar Bending Schedule."""
    st.header("Bar Bending Schedule (BBS) Generator")

    # --- Step 1: Add a Bar Mark ---
    with st.expander("Step 1: Add Bar Mark to Schedule", expanded=True):
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
                preferred_length = st.selectbox("Stock Bar Length", ["6m", "7.5m", "9m", "12m", "Optimal"], index=0)

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
                except Exception as e:
                    st.error(f"An error occurred: {e}")

    # --- Step 2: View Schedule & Order ---
    if st.session_state.schedule_df_list:
        with st.expander("Step 2: View Full Schedule & Generate Order Summary", expanded=True):
            full_schedule_df = pd.concat(st.session_state.schedule_df_list, ignore_index=True)
            st.dataframe(full_schedule_df)

            if st.button("📊 Generate Order Summary"):
                pivot_lengths, pivot_weights = Order_Details(full_schedule_df)
                if pivot_lengths is not None and pivot_weights is not None:
                    st.write("**Total Length to Order (meters)**")
                    st.dataframe(pivot_lengths)
                    st.write("**Total Weight to Order (kg)**")
                    st.dataframe(pivot_weights)

    # --- Step 3: AutoCAD Export (Windows Only)---
    if sys.platform == 'win32':
        with st.expander("Step 3: Export to AutoCAD"):
            if st.button("Connect to AutoCAD"):
                try:
                    st.session_state.acad_instance = Autocad(create_if_not_exists=True)
                    st.success(f"✅ Connected to AutoCAD: {st.session_state.acad_instance.doc.Name}")
                except Exception as e:
                    st.error(f"Could not connect to AutoCAD. Please ensure it is running. Details: {e}")
            
            if 'acad_instance' in st.session_state and st.session_state.acad_instance:
                table_list = get_table_info(st.session_state.acad_instance)
                if table_list:
                    selected_table = st.selectbox("Select Target Table in AutoCAD", table_list)
                    if selected_table:
                        handle = selected_table.split(',')[0].split(': ')[1]
                        start_row = st.number_input("Start inserting at row", min_value=1, value=2)
                        
                        if st.button("➡️ Export Schedule to AutoCAD Table"):
                            if st.session_state.schedule_df_list:
                                schedule_to_export = pd.concat(st.session_state.schedule_df_list, ignore_index=True).astype(str)
                                success, message = insert_df_into_table(st.session_state.acad_instance, handle, schedule_to_export, start_row)
                                if success: st.success(message)
                                else: st.error(message)
                            else:
                                st.warning("Schedule is empty.")
                else:
                    st.warning("No tables found in the active AutoCAD drawing.")

def standalone_calculators():
    """Page for individual calculation tools."""
    st.header("Standalone Rebar Calculators")

    tab1, tab2, tab3, tab4 = st.tabs(["Tonnage <> Lengths", "Cut Length", "Stirrup Cutting Length", "Optimal Bar Size"])

    with tab1:
        st.subheader("Tonnage & Bar Count Converter")
        c1, c2 = st.columns(2)
        diam_t = c1.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], key="t_diam")
        len_m = c2.selectbox("Standard Length", ["6m", "7.5m", "9m", "12m"], key="t_len")
        conv_type = st.radio("Conversion Type", ["Bars to Tonnage", "Tonnage to Bars"])

        if conv_type == "Bars to Tonnage":
            num_bars = st.number_input("Number of Bars", min_value=1, value=100)
            if st.button("Calculate Tonnage"):
                result = tonnage(num_bars, diam_t, len_m)
                st.metric("Calculated Tonnage", f"{result:.3f} tonnes")
        else:
            tonnage_val = st.number_input("Tonnage", min_value=0.1, value=1.0, step=0.1)
            if st.button("Calculate Number of Bars"):
                result = bars_lengths(tonnage_val, len_m, diam_t)
                st.metric("Calculated Number of Bars", f"{math.ceil(result)} bars")

    with tab2:
        st.subheader("Rebar Cut Length Calculator")
        lengths_cl_str = st.text_input("Lengths (comma-separated, in mm)", "250,1500,250", key="cl_len")
        diam_cl = st.selectbox("Diameter (mm)", [10, 12, 16, 20, 25, 32], key="cl_diam")
        bends_cl = st.number_input("Number of 90° Bends", min_value=0, value=2, key="cl_bends")
        if st.button("Calculate Cut Length"):
            try:
                lengths_cl = [int(l.strip()) for l in lengths_cl_str.split(',')]
                result_cl = Cutlength(lengths_cl, diam_cl, bends_cl)
                st.metric("Final Cut Length", f"{result_cl} mm")
            except ValueError: st.error("Please enter valid, comma-separated numbers for lengths.")

    with tab3:
        st.subheader("Stirrup Cutting Length Calculator")
        shape = st.selectbox("Stirrup Shape", ["Rectangle", "Square", "Circle"])
        perimeter = 0
        if shape == "Rectangle":
            l, w = st.number_input("Length (mm)", value=400), st.number_input("Width (mm)", value=300)
            perimeter = p_rectangle(l, w)
        elif shape == "Square":
            l_sq = st.number_input("Side Length (mm)", value=300)
            perimeter = p_square(l_sq)
        else:
            d_circ = st.number_input("Diameter (mm)", value=500)
            perimeter = p_circle(d_circ)
        
        diam_st = st.selectbox("Bar Diameter (mm)", [10, 12, 16, 20, 25, 32], key="st_diam")
        if st.button("Calculate Stirrup Cut Length"):
            result_st = stirrup_cutting_length(perimeter, diam_st)
            st.metric("Stirrup Cut Length", f"{result_st:.2f} mm")

    with tab4:
        st.subheader("Optimal Bar Size Calculator")
        cut_len_opt = st.number_input("Required Cut Length (m)", value=2.8, step=0.1, min_value=0.1)
        num_cuts_opt = st.number_input("Number of Cuts Needed", value=50, min_value=1)
        if st.button("Find Optimal Size"):
            size, bars_req = optimal_bar_size(cut_len_opt, num_cuts_opt)
            if size:
                st.metric("Optimal Stock Bar Size", f"{size} m")
                st.metric("Number of Stock Bars Required", f"{bars_req} bars")
            else: st.error(bars_req)


def main():
    """Main function to run the Streamlit app."""
    st.set_page_config(page_title="Rebar Engineering Suite", layout="wide", initial_sidebar_state="expanded")
    st.title("Rebar Engineering Suite 🏗️")

    if 'schedule_df_list' not in st.session_state:
        st.session_state.schedule_df_list = []

    st.sidebar.title("Navigation")
    app_mode = st.sidebar.radio("Choose a Tool", ["BBS Generator", "Standalone Calculators"])
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Clear Current Schedule", use_container_width=True):
        st.session_state.schedule_df_list = []
        st.toast("Schedule has been cleared!")

    st.sidebar.info("App by BarMate Fiji Ltd.")

    if app_mode == "BBS Generator":
        bbs_generator()
    else:
        standalone_calculators()


if __name__ == "__main__":
    main()
