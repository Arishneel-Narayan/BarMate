# Rebar Detailing and Optimization Toolkit

This Jupyter Notebook provides a comprehensive suite of tools for rebar detailing, scheduling, and material optimization.

The toolkit is designed to automate common structural engineering calculations, from determining the precise cutting length of a bar to finding the most efficient stock length to minimize material waste. It also includes an optional module for directly integrating with Autodesk AutoCAD to populate schedules.

## Key Features

* **Cut Length Calculation:** Automatically calculates rebar cutting lengths, accounting for standard bend deductions.
* **Weight & Quantity Conversion:** Easily convert between rebar tonnage and the number of bars for various diameters and lengths.
* **Waste Optimization:** Determines the most economical stock bar length (6m, 7.5m, 9m, 12m) to use for a given set of cuts, minimizing offcut waste.
* **Bar Bending Schedule Generation:** Uses `pandas` to create and manage structured, professional bar bending schedules.
* **AutoCAD Integration:** (Optional) Pushes the final schedule data directly into a table within a running AutoCAD drawing, automating documentation.

## Dependencies

The project requires the following Python libraries:

* `pandas`
* `matplotlib`
* `pyautocad`
* `jupyter`

Install them via pip:
```bash
pip install pandas matplotlib pyautocad jupyterlab
