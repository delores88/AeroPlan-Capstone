"""Explicit, user-reviewable CSV contracts. No assumptions about unseen Kaggle headers."""
SOURCE_URL = 'https://www.kaggle.com/datasets/robertocarlost/aerospace-supply-chain-performance-and-forecasting'
SOURCE_TITLE = 'Aerospace Supply Chain Performance & Forecasting'
TABLES = {
 'parts': {'filename': 'parts_master.csv', 'required': ['part_id','unit_cost','lead_time_days'], 'fields': {
  'part_id':['part_id','part_number','part','sku','partnumber'],
  'description':['description','part_name','part_description','name'],
  'family':['part_family','family','category'], 'criticality':['criticality','criticality_class','criticality_level'],
  'unit_cost':['unit_cost','unit_cost_usd','cost_per_unit','cost'],
  'lead_time_days':['nominal_lead_time_days','lead_time_days','nominal_lead_time','lead_time'],
  'supplier_id':['supplier_id_primary','supplier_id','primary_supplier_id','supplier'],
  'supplier_risk':['supplier_risk','supplier_risk_class','supplier_risk_classification'],
  'repairable':['repairable','is_repairable'], 'shelf_life_days':['shelf_life_days','shelf_life'] }},
 'history': {'filename':'supply_chain_history.csv', 'required':['site_id','part_id','week','demand'], 'fields': {
  'site_id':['site_id','site','plant_id','location_id','plant'], 'part_id':['part_id','part_number','part','sku'],
  'week':['week','week_start','week_start_date','date','week_date'],
  'demand':['actual_consumption','actual_demand','consumption','consumption_qty','actual_consumption_qty','demand','demand_qty'],
  'on_hand':['on_hand_inventory','on_hand_stock','inventory_on_hand','on_hand','on_hand_qty','stock_on_hand','inventory'],
  'backorders':['backorders','backorder_qty','backorder_quantity','backorder'],
  'blocked_stock':['blocked_stock','blocked_inventory','blocked_qty'],
  'baseline_forecast':['baseline_forecast','forecast_baseline','baseline_forecast_qty'],
  'adjusted_forecast':['adjusted_forecast','forecast_adjusted','consensus_forecast'],
  'maintenance_type':['maintenance_type','planned_unplanned_maintenance','maintenance_flag'] }},
 'orders': {'filename':'purchase_orders.csv','required':['part_id','order_date','receipt_date'], 'fields': {
  'po_id':['po_id','purchase_order_id','po_number','order_id'], 'part_id':['part_id','part_number','part','sku'],
  'site_id':['site_id','site','plant_id','location_id'], 'supplier_id':['supplier_id','supplier'],
  'order_date':['order_date','po_date','purchase_order_date','creation_date'],
  'promised_date':['promised_date','promised_delivery_date','promised_receipt_date','expected_delivery_date','due_date'],
  'receipt_date':['actual_receipt_date','actual_delivery_date','receipt_date','delivery_date'],
  'quantity':['quantity','order_quantity','ordered_quantity','ordered_qty','quantity_ordered','qty'],
  'received_quantity':['received_quantity','received_qty','quantity_received'] }},
 'quality': {'filename':'quality_incidents.csv','required':[], 'fields':{}}
}
