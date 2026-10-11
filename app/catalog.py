"""Equipment and supplies catalogue: what a department can request, grouped by catalogue department and category.

A broad list of commonly used hospital equipment, not a claim that every hospital needs every item. Final
procurement lists and quantities depend on the hospital's specialties, bed capacity, regulations and clinical needs.

Each entry: (name, tracking, needs_service). tracking is "asset" for individually tagged equipment and "quantity"
for consumables counted by stock. needs_service marks equipment with planned maintenance or calibration.
"""
from sqlalchemy import select

from .db import EquipmentCatalogItem

A, Q = "asset", "quantity"
ALL = "*"  # shared by every department

# section -> (hospital departments that usually request it, unit for consumables, {category: [items]})
CATALOG = {
    "Critical care and patient monitoring": (["Emergency", "Cardiology", "General Medicine", "Neurology", "Pediatrics"], {
        "Ventilation": [("ICU ventilator", A, True), ("Non-invasive ventilator (BiPAP/CPAP)", A, True),
                        ("Transport ventilator", A, True)],
        "Monitoring": [("Multiparameter patient monitor", A, True), ("Central monitoring station", A, True),
                       ("Pulse oximeter", A, True), ("Capnograph", A, True)],
        "Infusion": [("Infusion pump", A, True), ("Syringe pump", A, True)],
        "Resuscitation": [("Defibrillator", A, True), ("Crash cart", A, False), ("Laryngoscope set", A, False)],
    }),
    "Diagnostic instruments": ([ALL], {
        "Examination": [("Stethoscope", A, False), ("BP apparatus", A, True), ("Digital thermometer", A, False),
                        ("Otoscope and ophthalmoscope set", A, False), ("Examination lamp", A, False)],
        "Cardiac diagnostics": [("ECG machine", A, True), ("Holter monitor", A, True)],
        "Neurological examination": [("Reflex hammer", A, False), ("Tuning fork set", A, False), ("EEG machine", A, True)],
        "Point-of-care testing": [("Glucometer", A, True), ("Glucometer test strips", Q, False)],
    }),
    "Beds, mobility and patient handling": ([ALL], {
        "Beds": [("Hospital bed", A, True), ("ICU bed", A, True), ("Pediatric cot", A, False),
                 ("Infant radiant warmer", A, True)],
        "Mobility": [("Wheelchair", A, False), ("Stretcher trolley", A, False), ("Walker and crutches", A, False)],
    }),
    "Surgical instruments and tools": (["Orthopedics", "Emergency", "General Medicine"], {
        "Instruments": [("Surgical scissors", A, False), ("Artery forceps", A, False), ("Needle holder", A, False),
                        ("Scalpel handle", A, False), ("Orthopedic instrument set", A, False), ("Plaster cutter", A, True)],
        "Procedure kits": [("Suture kit", Q, False), ("Dressing set", Q, False)],
    }),
    "Medical consumables": ([ALL], {
        "Protective": [("Surgical gloves", Q, False), ("Face masks", Q, False), ("Disposable gowns", Q, False)],
        "Injection and IV": [("Syringes and needles", Q, False), ("IV cannulas", Q, False), ("IV fluids", Q, False),
                             ("Infusion sets", Q, False)],
        "Wound care": [("Gauze and bandages", Q, False), ("Sutures", Q, False)],
        "Respiratory": [("Oxygen masks", Q, False), ("Nebuliser", A, True), ("Nebuliser kits", Q, False)],
    }),
    "Spare parts and accessories": ([ALL], {
        "Replacement parts": [("Monitor ECG leads", Q, False), ("SpO2 sensor probe", Q, False), ("BP cuff", Q, False),
                              ("Ventilator breathing circuit", Q, False), ("Equipment batteries", Q, False)],
    }),
    # Sections 30 to 38 of the hospital equipment catalogue.
    "Ambulance and patient transport services": (["Emergency"], {
        "Vehicles": [("Basic-life-support ambulance", A, True), ("Advanced-life-support ambulance", A, True)],
        "Patient handling": [("Ambulance stretcher and loading system", A, True), ("Stair chair", A, False),
                             ("Transfer board", A, False), ("Immobilization devices and splints", Q, False)],
        "Oxygen and airway": [("Portable oxygen cylinder and regulator", A, True), ("Portable ventilator", A, True),
                              ("Portable suction unit", A, True), ("Bag-valve-mask and airway kit", Q, False)],
        "Resuscitation and monitoring": [("AED / defibrillator", A, True), ("Portable multiparameter monitor", A, True),
                                         ("Emergency medical bag", A, False)],
        "Communication": [("Communication radio and dispatch system", A, True)],
        "Consumables": [("PPE, emergency dressings and approved consumables", Q, False)],
    }),
    "Central oxygen, medical gases and vacuum systems": ([ALL], {
        "Supply plant": [("Medical oxygen supply system", A, True), ("Oxygen cylinder manifold", A, True),
                         ("Medical air compressor", A, True), ("Medical vacuum pump", A, True)],
        "Distribution": [("Gas pipeline distribution system", A, True), ("Bedhead gas outlet", A, True),
                         ("Pressure regulator and flowmeter", A, True)],
        "Alarms and safety": [("Gas pressure and alarm panel", A, True), ("Gas leak detection and monitoring system", A, True)],
        "Handling and storage": [("Cylinder trolley and storage rack", A, False)],
        "Testing": [("Pipeline testing and maintenance instruments", A, True)],
    }),
    "Hospital infection control and biomedical waste management": ([ALL], {
        "Hand hygiene and PPE": [("Hand hygiene station", A, False), ("PPE storage cabinet", A, False)],
        "Disinfection": [("Disinfection equipment", A, True), ("UV-C disinfection device (where approved)", A, True),
                         ("Washer-disinfector", A, True), ("Sterilization monitoring supplies", Q, False)],
        "Cleaning": [("Environmental cleaning cart", A, False), ("Cleaning equipment and chemical storage system", A, False)],
        "Biomedical waste": [("Sharps containers", Q, False), ("Colour-coded biomedical waste bins and bags", Q, False),
                             ("Waste weighing scale", A, True), ("Spill management kit", Q, False),
                             ("Dedicated waste transport trolley", A, False)],
    }),
    "Laundry and linen services": ([ALL], {
        "Machines": [("Industrial washing machine", A, True), ("Industrial dryer", A, True),
                     ("Steam ironing equipment", A, True), ("Flatwork ironer and folding machine", A, True),
                     ("Laundry chemical dosing system", A, True)],
        "Handling": [("Linen sorting table", A, False), ("Laundry cart and trolley", A, False),
                     ("Linen weighing scale", A, True), ("Clean-linen storage rack", A, False),
                     ("Soiled-linen container", A, False)],
        "Supplies": [("Bed linen", Q, False), ("Laundry PPE", Q, False)],
    }),
    "Hospital kitchen and dietary services": ([ALL], {
        "Cold storage": [("Commercial refrigerator and freezer", A, True), ("Cold-chain monitoring device", A, True)],
        "Cooking": [("Commercial cooking range", A, True), ("Steam kettle and oven", A, True)],
        "Preparation and serving": [("Food preparation table", A, False), ("Food transport trolley", A, False),
                                    ("Weighing scale and portioning equipment", A, True), ("Food storage containers", Q, False)],
        "Food safety": [("Temperature probe and food thermometer", A, True), ("Dishwasher", A, True),
                        ("Handwashing station", A, False), ("Food-safe cleaning equipment", Q, False)],
    }),
    "Mortuary and forensic services": ([], {
        "Storage and transfer": [("Mortuary refrigerator / body storage cabinet", A, True),
                                 ("Mortuary trolley and transfer stretcher", A, False)],
        "Examination": [("Autopsy table", A, False), ("Examination light", A, True), ("Suction system", A, True),
                        ("Instrument set", A, False), ("Specimen collection equipment", Q, False)],
        "Identification and safety": [("Body identification tags and barcode system", Q, False),
                                      ("PPE and protective equipment", Q, False),
                                      ("Cleaning and disinfection equipment", A, False),
                                      ("Temperature monitoring system", A, True)],
    }),
    "Hospital facilities and infrastructure maintenance": ([ALL], {
        "Power": [("Electrical distribution panel and backup power", A, True), ("Diesel generator", A, True),
                  ("UPS system", A, True), ("Emergency lighting", A, True)],
        "Building services": [("HVAC and air-handling equipment", A, True), ("Water pump and water treatment system", A, True),
                              ("Elevator and patient lift", A, True), ("Building management system", A, True),
                              ("Refrigeration and cold-room system", A, True),
                              ("Environmental temperature and humidity sensor", A, True)],
        "Fire safety": [("Fire extinguishers and fire alarm system", A, True)],
        "Workshop": [("Plumbing and drainage maintenance tools", A, False), ("Workshop tools and spare parts", Q, False)],
    }),
    "Hospital administration, reception and IT": ([ALL], {
        "Computers and printing": [("Desktop computer / laptop", A, True), ("Printer, scanner and barcode label printer", A, True),
                                   ("ID card printer", A, True), ("Document scanner and secure storage system", A, True)],
        "Front desk": [("Patient registration terminal", A, True), ("Queue management display", A, True),
                       ("Appointment kiosk", A, True), ("Electronic medical record workstation", A, True)],
        "Network and servers": [("Network switch and Wi-Fi access point", A, True), ("Server or approved cloud infrastructure", A, True),
                                ("UPS unit and network rack", A, True)],
        "Communication and security": [("CCTV system with controlled access", A, True), ("Telephone and intercom system", A, True),
                                       ("Nurse-call system", A, True)],
    }),
    "Mortality prevention, safety and general patient support": ([ALL], {
        "Mobility and transfer": [("Wheelchair / transport chair", A, False), ("Patient lift and transfer aid", A, True),
                                  ("Handrails and mobility supports", A, False), ("Accessible bathroom aids", A, False)],
        "Alarms and calls": [("Fall-prevention alarm", A, True), ("Bedside call bell / nurse-call device", A, True)],
        "Pressure care": [("Pressure-relief mattress", A, False)],
        "Safety": [("Emergency lighting (ward)", A, True), ("Portable fire extinguisher", A, True),
                   ("Spill kit and first-aid kit", Q, False), ("Safety signs and barriers", Q, False)],
        "Identification": [("Patient identification wristbands", Q, False), ("Wristband scanner", A, True)],
    }),
}

UNITS = {Q: "pack", A: "unit"}


def rows():
    for section, (departments, categories) in CATALOG.items():
        for category, items in categories.items():
            for name, tracking, service in items:
                yield {"section": section, "category": category, "name": name, "tracking": tracking,
                       "unit": UNITS[tracking], "departments": ",".join(departments), "needs_service": service}


def ensure_catalog(db):
    """Insert catalogue entries that are missing. Existing entries and anything linked to them are left alone."""
    have = {(c.section, c.name) for c in db.scalars(select(EquipmentCatalogItem))}
    added = 0
    for row in rows():
        if (row["section"], row["name"]) not in have:
            db.add(EquipmentCatalogItem(**row))
            added += 1
    if added:
        db.commit()
    return added
