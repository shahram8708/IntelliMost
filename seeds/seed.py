import logging
import random
import secrets
from datetime import datetime, date, timedelta

from app.extensions import db, bcrypt
from app.models.alert import AlertEvent, AlertRule
from app.models.audit_log import AuditLog
from app.models.capa import CapaComment, CapaRecord
from app.models.downtime import DowntimeEvent
from app.models.improvement import ImprovementOpportunity
from app.models.lead import Lead
from app.models.machine import Machine
from app.models.most_element import MostElement
from app.models.most_study import MostStudy
from app.models.plant import Plant
from app.models.production_line import ProductionLine
from app.models.rca import RcaRecord
from app.models.reason_code import ReasonCode
from app.models.rejection import RejectionEvent
from app.models.shift import ProductionOutput, Shift
from app.models.sku import SKU
from app.models.user import User
from app.models.user_preference import UserPreference
from app.services.most_calculator import calculate_element_tmu, calculate_standard_time
from app.services.oee_calculator import calculate_oee

log = logging.getLogger(__name__)

_rng = random.Random(20240901)
NOW = datetime.utcnow()
TODAY = date.today()
SEED_PASSWORDS = {
    "super_admin": "SuperAdmin@2024",
    "admin": "Admin@2024",
    "plant_manager": "PlantManager@2024",
    "industrial_engineer": "IndustrialEngineer@2024",
    "qa_manager": "QAManager@2024",
    "shift_supervisor": "ShiftSupervisor@2024",
    "operator": "Operator@2024",
}
UA_DESK = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
UA_MOB = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 Chrome/124.0.0.0 Mobile Safari/537.36"
)
VALID_IDX = [0, 1, 3, 6, 10, 16, 24, 32]
SAMPLE_IPS = [
    "10.0.1.15", "10.0.1.22", "10.0.2.8",
    "192.168.1.45", "192.168.1.67", "172.16.0.12",
]


def _ip():
    return _rng.choice(SAMPLE_IPS)


def _ago(days=0, hours=0, minutes=0):
    return NOW - timedelta(days=days, hours=hours, minutes=minutes)


def _agodate(days=0):
    return TODAY - timedelta(days=days)


def _pw(role):
    return bcrypt.generate_password_hash(SEED_PASSWORDS[role], rounds=12).decode("utf-8")


def _audit(uid, action, ttype=None, tid=None, desc=None, when=None, ua=None):
    return AuditLog(
        user_id=uid, action=action, target_type=ttype, target_id=tid,
        description=desc, ip_address=_ip(), user_agent=ua or UA_DESK,
        created_at=when or NOW,
    )


def _oee_inline(shift, dur_hours, break_min):
    """
    Exact mirror of services/oee_calculator.calculate_oee() with no db.commit().
    Used for completed historical shifts so we can batch-commit every 40 shifts.
    """
    planned = (dur_hours * 60.0) - break_min
    if planned <= 0:
        planned = 1.0
    unplanned_dt = sum(
        (e.duration_minutes or 0) for e in shift.downtime_events
        if e.event_type == "unplanned" and e.duration_minutes
    )
    operating = max(planned - unplanned_dt, 0.0)
    avail = operating / planned if planned > 0 else 0.0
    ideal_cycle = planned / shift.target_units if shift.target_units > 0 else 0.0
    perf = min(
        (ideal_cycle * shift.actual_units) / operating
        if operating > 0 and shift.actual_units else 0.0,
        1.0,
    )
    good = (shift.actual_units or 0) - (shift.rejection_count or 0)
    qual = good / shift.actual_units if shift.actual_units and shift.actual_units > 0 else 0.0
    oee = avail * perf * qual
    shift.oee_percent = round(oee * 100, 2)
    shift.availability_percent = round(avail * 100, 2)
    shift.performance_percent = round(perf * 100, 2)
    shift.quality_percent = round(qual * 100, 2)


def _current_shift_start():
    base = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = base - timedelta(days=1)
    for start in [
        base + timedelta(hours=16, minutes=30),
        base + timedelta(hours=8, minutes=30),
        base + timedelta(hours=0, minutes=30),
        yesterday + timedelta(hours=16, minutes=30),
    ]:
        if start <= NOW <= start + timedelta(hours=8):
            return start
    return NOW - timedelta(hours=3)


def run_seed():
    """Called by create_app() when the database has no users."""
    if Plant.query.first():
        log.info("Seed guard: data already present, skipping.")
        return
    try:
        _seed()
    except Exception:
        db.session.rollback()
        log.exception("Seed failed — transaction rolled back.")
        raise


def _seed():
    log.info("IntelliMOST seed starting ...")
    ctx = _build_master_data()
    perf = _build_historical_shifts(ctx)
    active = _build_active_shifts(ctx)
    _build_most_studies(ctx)
    rules = _build_alert_rules(ctx)
    evts_for_capa = _build_alert_events(ctx, rules, active)
    capas = _build_capas(ctx, evts_for_capa)
    _build_rca(ctx, capas)
    _build_improvements(ctx, perf)
    _build_preferences_and_leads(ctx)
    _build_audit_logs(ctx, capas)
    _print_summary(ctx)
    log.info("IntelliMOST seed complete.")


def _build_master_data():
    p1 = Plant(
        name="Pharma Excellence Ltd",
        location="Pune, Maharashtra, India",
        timezone="Asia/Kolkata",
        industry_type="pharmaceutical",
        subscription_tier="enterprise",
        subscription_active=True,
        contact_email="ops@pharmaexcellence.in",
        contact_phone="+91-20-4456-7890",
        is_active=True,
        created_at=_ago(days=180),
    )
    p2 = Plant(
        name="NutriCraft Foods Pvt Ltd",
        location="Ahmedabad, Gujarat, India",
        timezone="Asia/Kolkata",
        industry_type="FMCG",
        subscription_tier="professional",
        subscription_active=True,
        contact_email="production@nutricraftfoods.com",
        contact_phone="+91-79-2670-1234",
        is_active=True,
        created_at=_ago(days=150),
    )
    p3 = Plant(
        name="ChemFlow Process Industries",
        location="Navi Mumbai, Maharashtra, India",
        timezone="Asia/Kolkata",
        industry_type="process manufacturing",
        subscription_tier="starter",
        subscription_active=True,
        contact_email="plant@chemflowindia.com",
        contact_phone="+91-22-6745-3210",
        is_active=True,
        created_at=_ago(days=120),
    )
    db.session.add_all([p1, p2, p3])
    db.session.flush()

    ph = None
    sa = User(
        email="rajesh.sharma@intellimost.io", password_hash=ph,
        full_name="Rajesh Kumar Sharma", role="super_admin", plant_id=None,
        is_active=True, phone="+91-98765-43210",
        department="Platform Administration", last_login=_ago(hours=2),
        created_at=_ago(days=180),
    )
    adm = User(
        email="priya.mehta@intellimost.io", password_hash=ph,
        full_name="Priya Mehta", role="admin", plant_id=None,
        is_active=True, phone="+91-98700-12345",
        department="Customer Success", last_login=_ago(hours=5),
        created_at=_ago(days=160),
    )
    p1_pm = User(
        email="anita.desai@pharmaexcellence.in", password_hash=ph,
        full_name="Dr. Anita Desai", role="plant_manager", plant_id=p1.id,
        department="Operations", phone="+91-98201-55678",
        last_login=_ago(hours=3), created_at=_ago(days=170),
    )
    p1_ie1 = User(
        email="suresh.patel@pharmaexcellence.in", password_hash=ph,
        full_name="Suresh Vinod Patel", role="industrial_engineer", plant_id=p1.id,
        department="Industrial Engineering", phone="+91-98202-11234",
        most_certification_level="MOST Practitioner Level II",
        last_login=_ago(hours=4), created_at=_ago(days=168),
    )
    p1_ie2 = User(
        email="kavitha.nair@pharmaexcellence.in", password_hash=ph,
        full_name="Kavitha Rajan Nair", role="industrial_engineer", plant_id=p1.id,
        department="Industrial Engineering", phone="+91-98203-22345",
        most_certification_level="MOST Practitioner Level I",
        last_login=_ago(days=2), created_at=_ago(days=155),
    )
    p1_qa = User(
        email="vinod.kulkarni@pharmaexcellence.in", password_hash=ph,
        full_name="Vinod Narayan Kulkarni", role="qa_manager", plant_id=p1.id,
        department="Quality Assurance", phone="+91-98204-33456",
        last_login=_ago(hours=6), created_at=_ago(days=165),
    )
    p1_sup1 = User(
        email="ramesh.tiwari@pharmaexcellence.in", password_hash=ph,
        full_name="Ramesh Kumar Tiwari", role="shift_supervisor", plant_id=p1.id,
        department="Production", phone="+91-98205-44567",
        last_login=_ago(hours=1), created_at=_ago(days=160),
    )
    p1_sup2 = User(
        email="sunita.yadav@pharmaexcellence.in", password_hash=ph,
        full_name="Sunita Devi Yadav", role="shift_supervisor", plant_id=p1.id,
        department="Production", phone="+91-98206-55678",
        last_login=_ago(hours=9), created_at=_ago(days=158),
    )
    p1_sup3 = User(
        email="mahesh.gupta@pharmaexcellence.in", password_hash=ph,
        full_name="Mahesh Chandra Gupta", role="shift_supervisor", plant_id=p1.id,
        department="Production", phone="+91-98207-66789",
        last_login=_ago(days=1), created_at=_ago(days=155),
    )
    p1_op1 = User(
        email="arun.singh@pharmaexcellence.in", password_hash=ph,
        full_name="Arun Kumar Singh", role="operator", plant_id=p1.id,
        department="Production", last_login=_ago(hours=2),
        created_at=_ago(days=150),
    )
    p1_op2 = User(
        email="deepa.verma@pharmaexcellence.in", password_hash=ph,
        full_name="Deepa Rajesh Verma", role="operator", plant_id=p1.id,
        department="Production", is_locked=True, failed_login_attempts=5,
        last_login=_ago(days=3), created_at=_ago(days=145),
    )
    p1_op3 = User(
        email="sanjay.kumar@pharmaexcellence.in", password_hash=ph,
        full_name="Sanjay Prakash Kumar", role="operator", plant_id=p1.id,
        department="Production", last_login=_ago(hours=3),
        created_at=_ago(days=140),
    )
    inv_tok = secrets.token_hex(32)
    p1_op4 = User(
        email="pooja.sharma@pharmaexcellence.in", password_hash=None,
        full_name="Pooja Arvind Sharma", role="operator", plant_id=p1.id,
        department="Production", is_active=False,
        invitation_token=inv_tok,
        invitation_expires_at=NOW + timedelta(days=3),
        created_at=_ago(days=1),
    )
    p2_pm = User(
        email="mohan.agarwal@nutricraftfoods.com", password_hash=ph,
        full_name="Mohan Lal Agarwal", role="plant_manager", plant_id=p2.id,
        department="Operations", phone="+91-97253-12345",
        last_login=_ago(hours=4), created_at=_ago(days=145),
    )
    p2_ie = User(
        email="preeti.joshi@nutricraftfoods.com", password_hash=ph,
        full_name="Preeti Sunil Joshi", role="industrial_engineer", plant_id=p2.id,
        department="Industrial Engineering", phone="+91-97254-23456",
        most_certification_level="MOST Analyst Level I",
        last_login=_ago(hours=5), created_at=_ago(days=140),
    )
    p2_qa = User(
        email="dilip.shah@nutricraftfoods.com", password_hash=ph,
        full_name="Dilip Kiran Shah", role="qa_manager", plant_id=p2.id,
        department="Quality Control", phone="+91-97255-34567",
        last_login=_ago(hours=7), created_at=_ago(days=138),
    )
    p2_sup1 = User(
        email="vijay.rathore@nutricraftfoods.com", password_hash=ph,
        full_name="Vijay Singh Rathore", role="shift_supervisor", plant_id=p2.id,
        department="Production", phone="+91-97256-45678",
        last_login=_ago(hours=2), created_at=_ago(days=135),
    )
    p2_sup2 = User(
        email="meena.kapoor@nutricraftfoods.com", password_hash=ph,
        full_name="Meena Rajesh Kapoor", role="shift_supervisor", plant_id=p2.id,
        department="Production", phone="+91-97257-56789",
        last_login=_ago(hours=11), created_at=_ago(days=132),
    )
    p2_op1 = User(
        email="raju.mishra@nutricraftfoods.com", password_hash=ph,
        full_name="Raju Prasad Mishra", role="operator", plant_id=p2.id,
        department="Production", last_login=_ago(hours=3),
        created_at=_ago(days=130),
    )
    p2_op2 = User(
        email="geeta.pandey@nutricraftfoods.com", password_hash=ph,
        full_name="Geeta Bhushan Pandey", role="operator", plant_id=p2.id,
        department="Production", last_login=_ago(hours=4),
        created_at=_ago(days=128),
    )
    p2_op3 = User(
        email="prakash.rao@nutricraftfoods.com", password_hash=ph,
        full_name="Prakash Venkat Rao", role="operator", plant_id=p2.id,
        department="Production", is_active=False, is_deleted=True,
        last_login=_ago(days=45), created_at=_ago(days=125),
    )
    p3_pm = User(
        email="aditya.nambiar@chemflowindia.com", password_hash=ph,
        full_name="Aditya Krishna Nambiar", role="plant_manager", plant_id=p3.id,
        department="Operations", phone="+91-96540-12345",
        last_login=_ago(hours=6), created_at=_ago(days=115),
    )
    p3_ie = User(
        email="rohini.bhat@chemflowindia.com", password_hash=ph,
        full_name="Rohini Suresh Bhat", role="industrial_engineer", plant_id=p3.id,
        department="Process Engineering", phone="+91-96541-23456",
        most_certification_level="MOST Analyst Level I",
        last_login=_ago(hours=8), created_at=_ago(days=112),
    )
    p3_qa = User(
        email="sunil.khatri@chemflowindia.com", password_hash=ph,
        full_name="Sunil Ramesh Khatri", role="qa_manager", plant_id=p3.id,
        department="Quality and HSE", phone="+91-96542-34567",
        last_login=_ago(hours=10), created_at=_ago(days=110),
    )
    p3_sup = User(
        email="dinesh.malhotra@chemflowindia.com", password_hash=ph,
        full_name="Dinesh Raj Malhotra", role="shift_supervisor", plant_id=p3.id,
        department="Production", phone="+91-96543-45678",
        last_login=_ago(hours=3), created_at=_ago(days=108),
    )
    p3_op1 = User(
        email="rekha.soni@chemflowindia.com", password_hash=ph,
        full_name="Rekha Prakash Soni", role="operator", plant_id=p3.id,
        department="Production", last_login=_ago(hours=4),
        created_at=_ago(days=106),
    )
    p3_op2 = User(
        email="tarun.jain@chemflowindia.com", password_hash=ph,
        full_name="Tarun Vijay Jain", role="operator", plant_id=p3.id,
        department="Production", last_login=_ago(hours=5),
        created_at=_ago(days=104),
    )

    all_users = [
        sa, adm,
        p1_pm, p1_ie1, p1_ie2, p1_qa, p1_sup1, p1_sup2, p1_sup3,
        p1_op1, p1_op2, p1_op3, p1_op4,
        p2_pm, p2_ie, p2_qa, p2_sup1, p2_sup2, p2_op1, p2_op2, p2_op3,
        p3_pm, p3_ie, p3_qa, p3_sup, p3_op1, p3_op2,
    ]
    for u in all_users:
        if not u.invitation_token:
            u.password_hash = _pw(u.role)
    db.session.add_all(all_users)
    db.session.flush()

    l_tcla = ProductionLine(
        plant_id=p1.id, line_name="Tablet Compression Line A", line_code="TCL-A",
        target_output_per_shift=5000, shift_duration_hours=8.0,
        planned_break_minutes=30, created_at=_ago(days=175),
    )
    l_cflb = ProductionLine(
        plant_id=p1.id, line_name="Capsule Filling Line B", line_code="CFL-B",
        target_output_per_shift=4000, shift_duration_hours=8.0,
        planned_break_minutes=30, created_at=_ago(days=174),
    )
    l_bplc = ProductionLine(
        plant_id=p1.id, line_name="Blistering and Packaging Line C", line_code="BPL-C",
        target_output_per_shift=8000, shift_duration_hours=8.0,
        planned_break_minutes=30, created_at=_ago(days=173),
    )
    l_bpl1 = ProductionLine(
        plant_id=p2.id, line_name="Biscuit Production Line 1", line_code="BPL-1",
        target_output_per_shift=12000, shift_duration_hours=8.0,
        planned_break_minutes=30, created_at=_ago(days=145),
    )
    l_ccl2 = ProductionLine(
        plant_id=p2.id, line_name="Confectionery Coating Line 2", line_code="CCL-2",
        target_output_per_shift=8000, shift_duration_hours=8.0,
        planned_break_minutes=30, created_at=_ago(days=144),
    )
    l_cbla = ProductionLine(
        plant_id=p3.id, line_name="Chemical Blending Line Alpha", line_code="CBL-A",
        target_output_per_shift=1800, shift_duration_hours=8.0,
        planned_break_minutes=20, created_at=_ago(days=118),
    )
    l_dflb = ProductionLine(
        plant_id=p3.id, line_name="Distillation and Filling Line Beta", line_code="DFL-B",
        target_output_per_shift=1200, shift_duration_hours=8.0,
        planned_break_minutes=20, created_at=_ago(days=117),
    )
    all_lines = [l_tcla, l_cflb, l_bplc, l_bpl1, l_ccl2, l_cbla, l_dflb]
    db.session.add_all(all_lines)
    db.session.flush()

    mdef = [
        ("TCA-001","Rotary Tablet Press",              "Tablet Press",  "Fette Compacting",      "PT-3090",     2020,l_tcla.id),
        ("TCA-002","High-Speed Granulator",            "Granulator",    "GEA Group",             "PMA-800",     2019,l_tcla.id),
        ("TCA-003","Fluid Bed Dryer",                  "Dryer",         "Glatt GmbH",            "FBD-300",     2021,l_tcla.id),
        ("TCA-004","Tablet Coating Machine",           "Coater",        "IMA Active",            "XCT-50",      2020,l_tcla.id),
        ("CFB-001","Automatic Capsule Filling Machine","Capsule Filler","MG2 Pharma",            "FUTURA",      2021,l_cflb.id),
        ("CFB-002","Capsule Polishing Machine",        "Polisher",      "ACG Pharma",            "CP-200",      2019,l_cflb.id),
        ("CFB-003","Capsule Inspection System",        "Inspection",    "Videojet Technologies", "CSI-50",      2022,l_cflb.id),
        ("BPC-001","Blister Forming Machine",          "Blister Former","Uhlmann Group",         "B1240",       2020,l_bplc.id),
        ("BPC-002","Cartoning Machine",                "Cartoner",      "IMA Active",            "C45",         2021,l_bplc.id),
        ("BPC-003","Shrink Wrap Machine",              "Shrink Wrapper","Minipack Torre",        "SW-600",      2019,l_bplc.id),
        ("BPL-001","Biscuit Forming and Baking Oven", "Oven",          "Baker Perkins",         "TG-400",      2020,l_bpl1.id),
        ("BPL-002","Cooling Conveyor System",          "Conveyor",      "Heat and Control",      "CC-80M",      2019,l_bpl1.id),
        ("BPL-003","Cream Sandwiching Machine",        "Sandwicher",    "Haas Food Equipment",   "SMX-600",     2021,l_bpl1.id),
        ("CCL-001","Chocolate Enrobing Machine",       "Enrober",       "Sollich GmbH",          "Trienromat",  2020,l_ccl2.id),
        ("CCL-002","Cooling Tunnel",                   "Cooler",        "Aqua Cooling Systems",  "CT-120",      2019,l_ccl2.id),
        ("CCL-003","Primary Packaging Machine",        "Packager",      "SACMI Group",           "PVM-900",     2021,l_ccl2.id),
        ("CBA-001","Stainless Steel Batch Reactor",    "Reactor",       "De Dietrich Process",   "BR-2000",     2018,l_cbla.id),
        ("CBA-002","Centrifugal Pump and Transfer",    "Pump",          "KSB SE",                "Etanorm-90",  2019,l_cbla.id),
        ("DFB-001","Distillation Column",              "Distillation",  "Koch-Glitsch",          "FLEXIPAC-HC", 2017,l_dflb.id),
        ("DFB-002","Drum Filling Station",             "Filler",        "Flexicon Corporation",  "FC-100",      2020,l_dflb.id),
    ]
    machines = {}
    machines_by_line = {}
    for code, name, mtype, mfr, model, yr, lid in mdef:
        m = Machine(
            line_id=lid, machine_name=name, machine_code=code,
            machine_type=mtype, manufacturer=mfr, model_number=model,
            installation_date=date(yr, 3, 15), is_active=True,
            created_at=_ago(days=170),
        )
        db.session.add(m)
        machines[code] = m
        machines_by_line.setdefault(lid, []).append(m)
    db.session.flush()

    skus_raw = {
        p1.id: [
            ("PCT-500", "Paracetamol 500mg Tablets",               "tablets",  5000),
            ("AMX-250C","Amoxicillin 250mg Capsules",              "capsules", 2000),
            ("MET-500T","Metformin 500mg Tablets",                 "tablets",  5000),
            ("AML-5T",  "Amlodipine 5mg Tablets",                  "tablets",  3000),
            ("AZI-500T","Azithromycin 500mg Tablets",              "tablets",  1500),
            ("CET-10T", "Cetirizine 10mg Tablets",                 "tablets",  3000),
            ("OFX-200C","Ofloxacin 200mg Capsules",                "capsules", 1000),
            ("PAN-40T", "Pantoprazole 40mg Tablets",               "tablets",  3000),
            ("ATV-10T", "Atorvastatin 10mg Tablets",               "tablets",  3000),
            ("IBP-400T","Ibuprofen 400mg Tablets",                 "tablets",  3000),
        ],
        p2.id: [
            ("BCT-CHOC","Chocolate Sandwich Biscuit 100g",         "packs",    500),
            ("BCT-CREAM","Cream Biscuit Assorted 200g",            "packs",    500),
            ("BCT-SALT","Salted Cracker Assorted 300g",            "packs",    500),
            ("CCF-MILK","Milk Chocolate Enrobed Wafer 50g",        "packs",    200),
            ("CCF-DARK","Dark Chocolate Praline Box 150g",         "packs",    200),
            ("CCF-WHITE","White Chocolate Truffle Collection 200g","packs",    200),
            ("SNK-MIX", "Party Mix Snack 150g",                    "packs",    500),
            ("SNK-NUTS","Premium Roasted Cashew 250g",             "packs",    250),
        ],
        p3.id: [
            ("IPA-99",  "Isopropyl Alcohol 99% Pure 200L Drum",   "drums",    20),
            ("ACT-001", "Acetone 99.5% Reagent Grade 200L Drum",  "drums",    20),
            ("HCL-32",  "Hydrochloric Acid 32% Solution 250L IBC","IBC",      15),
            ("NaOH-50", "Sodium Hydroxide 50% Solution 250L IBC", "IBC",      15),
            ("MEK-001", "Methyl Ethyl Ketone Anhydrous 200L Drum","drums",    20),
            ("ETA-95",  "Ethanol 95% USP Grade 250L IBC",         "IBC",      15),
        ],
    }
    skus = {}
    skus_by_plant = {}
    for pid, items in skus_raw.items():
        skus_by_plant[pid] = []
        for code, name, uom, bs in items:
            s = SKU(
                plant_id=pid, sku_code=code, sku_name=name,
                unit_of_measure=uom, standard_batch_size=bs,
                is_active=True, created_at=_ago(days=160),
            )
            db.session.add(s)
            skus[code] = s
            skus_by_plant[pid].append(s)
    db.session.flush()

    rc_defs = [
        ("EF",      "Equipment Failure",                      "equipment_failure",  1, None),
        ("PM",      "Planned Maintenance",                    "planned_maintenance", 1, None),
        ("CO",      "Changeover",                             "changeover",          1, None),
        ("PI",      "Process Issue",                          "process",             1, None),
        ("UT",      "Utilities",                              "utilities",           1, None),
        ("QH",      "Quality Hold",                           "quality",             1, None),
        ("OT",      "Other",                                  "other",               1, None),
        ("EF-MF",   "Mechanical Failure",                     "equipment_failure",  2, "EF"),
        ("EF-EL",   "Electrical and Electronics Fault",       "equipment_failure",  2, "EF"),
        ("PM-PV",   "Preventive Maintenance",                 "planned_maintenance", 2, "PM"),
        ("PM-CV",   "Calibration and Validation",             "planned_maintenance", 2, "PM"),
        ("CO-PC",   "Product Changeover",                     "changeover",          2, "CO"),
        ("CO-MC",   "Material Changeover",                    "changeover",          2, "CO"),
        ("PI-MP",   "Material Problem",                       "process",             2, "PI"),
        ("PI-PP",   "Process Parameter Deviation",            "process",             2, "PI"),
        ("UT-PS",   "Power Supply Issue",                     "utilities",           2, "UT"),
        ("UT-CA",   "Compressed Air and Cooling Utilities",   "utilities",           2, "UT"),
        ("QH-IP",   "In-Process Quality Failure",             "quality",             2, "QH"),
        ("QH-FP",   "Finished Product Hold",                  "quality",             2, "QH"),
        ("OT-EX",   "External Factor",                        "other",               2, "OT"),
        ("OT-AD",   "Administrative and Documentation",       "other",               2, "OT"),
        ("EF-MF-01","Bearing and Shaft Failure",              "equipment_failure",  3, "EF-MF"),
        ("EF-MF-02","Belt and Chain Breakage",                "equipment_failure",  3, "EF-MF"),
        ("EF-MF-03","Gear and Coupling Wear",                 "equipment_failure",  3, "EF-MF"),
        ("EF-MF-04","Seal and Gasket Leakage",                "equipment_failure",  3, "EF-MF"),
        ("EF-EL-01","Sensor and Probe Malfunction",           "equipment_failure",  3, "EF-EL"),
        ("EF-EL-02","Motor and Drive Unit Failure",           "equipment_failure",  3, "EF-EL"),
        ("EF-EL-03","PLC and HMI Control Fault",              "equipment_failure",  3, "EF-EL"),
        ("PM-PV-01","Scheduled Preventive Maintenance",       "planned_maintenance", 3, "PM-PV"),
        ("PM-PV-02","Lubrication and Greasing Service",       "planned_maintenance", 3, "PM-PV"),
        ("PM-PV-03","Filter and Strainer Replacement",        "planned_maintenance", 3, "PM-PV"),
        ("PM-CV-01","Instrument Calibration",                 "planned_maintenance", 3, "PM-CV"),
        ("PM-CV-02","IQ OQ PQ Process Validation",           "planned_maintenance", 3, "PM-CV"),
        ("CO-PC-01","Product Format and Mould Change",        "changeover",          3, "CO-PC"),
        ("CO-PC-02","Die and Punch Set Change",               "changeover",          3, "CO-PC"),
        ("CO-PC-03","CIP and SIP Cleaning Cycle",             "changeover",          3, "CO-PC"),
        ("CO-MC-01","Raw Material Batch Changeover",          "changeover",          3, "CO-MC"),
        ("CO-MC-02","Packaging Material Changeover",          "changeover",          3, "CO-MC"),
        ("PI-MP-01","Out-of-Spec Raw Material Rejection",     "process",             3, "PI-MP"),
        ("PI-MP-02","Material Shortage and Delayed Delivery", "process",             3, "PI-MP"),
        ("PI-MP-03","Incorrect Batch Formulation",            "process",             3, "PI-MP"),
        ("PI-PP-01","Temperature Out of Operating Range",     "process",             3, "PI-PP"),
        ("PI-PP-02","Pressure and Flow Rate Deviation",       "process",             3, "PI-PP"),
        ("UT-PS-01","Power Interruption and Trip",            "utilities",           3, "UT-PS"),
        ("UT-PS-02","Voltage Fluctuation and Spike",          "utilities",           3, "UT-PS"),
        ("UT-CA-01","Low Compressed Air Pressure",            "utilities",           3, "UT-CA"),
        ("UT-CA-02","Cooling Water System Failure",           "utilities",           3, "UT-CA"),
        ("QH-IP-01","Weight and Content Uniformity Failure",  "quality",             3, "QH-IP"),
        ("QH-IP-02","Dissolution and Disintegration Failure", "quality",             3, "QH-IP"),
        ("QH-IP-03","Hardness and Texture Failure",           "quality",             3, "QH-IP"),
        ("QH-FP-01","Visual and Cosmetic Defect",             "quality",             3, "QH-FP"),
        ("QH-FP-02","Labelling and Coding Error",             "quality",             3, "QH-FP"),
        ("OT-EX-01","Supplier Delay and Short Delivery",      "other",               3, "OT-EX"),
        ("OT-EX-02","Customer and Regulatory Hold Request",   "other",               3, "OT-EX"),
        ("OT-AD-01","Awaiting QA and Regulatory Approval",   "other",               3, "OT-AD"),
        ("OT-AD-02","Documentation and GMP Record Pending",  "other",               3, "OT-AD"),
    ]
    rc_by_code = {}
    for code, label, cat, level, parent_code in rc_defs:
        pid_rc = rc_by_code[parent_code].id if parent_code else None
        rc = ReasonCode(
            plant_id=None, code=code, label=label,
            category=cat, level=level, parent_id=pid_rc, is_active=True,
        )
        db.session.add(rc)
        db.session.flush()
        rc_by_code[code] = rc

    db.session.commit()

    _unplanned_pool = [
        (rc_by_code["EF-MF-01"], 35), (rc_by_code["EF-MF-02"], 10),
        (rc_by_code["EF-EL-01"],  8), (rc_by_code["EF-EL-02"],  7),
        (rc_by_code["EF-MF-03"],  6), (rc_by_code["PI-PP-01"],  5),
        (rc_by_code["UT-PS-01"],  5), (rc_by_code["UT-CA-01"],  5),
        (rc_by_code["EF-EL-03"],  4), (rc_by_code["EF-MF-04"],  4),
        (rc_by_code["UT-PS-02"],  3), (rc_by_code["UT-CA-02"],  3),
        (rc_by_code["PI-PP-02"],  3), (rc_by_code["QH-IP-01"],  2),
    ]
    unplanned_codes   = [r for r, _ in _unplanned_pool]
    unplanned_weights = [w for _, w in _unplanned_pool]
    changeover_codes  = [rc_by_code["CO-PC-01"], rc_by_code["CO-PC-02"], rc_by_code["CO-PC-03"]]

    return {
        "p1": p1, "p2": p2, "p3": p3,
        "plants": [p1, p2, p3],
        "sa": sa, "adm": adm,
        "all_users": all_users,
        "all_lines": all_lines,
        "machines": machines,
        "machines_by_line": machines_by_line,
        "skus": skus,
        "skus_by_plant": skus_by_plant,
        "rc_by_code": rc_by_code,
        "unplanned_codes": unplanned_codes,
        "unplanned_weights": unplanned_weights,
        "changeover_codes": changeover_codes,
        "l_tcla": l_tcla, "l_cflb": l_cflb, "l_bplc": l_bplc,
        "l_bpl1": l_bpl1, "l_ccl2": l_ccl2,
        "l_cbla": l_cbla, "l_dflb": l_dflb,
        "sups": {
            p1.id: [p1_sup1, p1_sup2, p1_sup3],
            p2.id: [p2_sup1, p2_sup2],
            p3.id: [p3_sup],
        },
        "ops": {
            p1.id: [p1_op1, p1_op3],
            p2.id: [p2_op1, p2_op2],
            p3.id: [p3_op1, p3_op2],
        },
        "ies": {p1.id: [p1_ie1, p1_ie2], p2.id: [p2_ie], p3.id: [p3_ie]},
        "qa":  {p1.id: p1_qa,  p2.id: p2_qa,  p3.id: p3_qa},
        "pm":  {p1.id: p1_pm,  p2.id: p2_pm,  p3.id: p3_pm},
        "p1_pm": p1_pm, "p1_ie1": p1_ie1, "p1_ie2": p1_ie2, "p1_qa": p1_qa,
        "p1_sup1": p1_sup1, "p1_sup2": p1_sup2, "p1_sup3": p1_sup3,
        "p1_op1": p1_op1,   "p1_op2": p1_op2,   "p1_op3": p1_op3,
        "p1_op4": p1_op4,
        "p2_pm": p2_pm, "p2_ie": p2_ie, "p2_qa": p2_qa,
        "p2_sup1": p2_sup1, "p2_sup2": p2_sup2, "p2_op2": p2_op2,
        "p2_op3": p2_op3,
        "p3_pm": p3_pm, "p3_ie": p3_ie, "p3_qa": p3_qa, "p3_sup": p3_sup,
        "p3_op1": p3_op1,
    }


def _build_historical_shifts(ctx):
    HISTORY_DAYS = 60
    SHIFT_OFFSETS = [
        (timedelta(hours=0,  minutes=30), "A"),
        (timedelta(hours=8,  minutes=30), "B"),
        (timedelta(hours=16, minutes=30), "C"),
    ]
    uc = ctx["unplanned_codes"]
    uw = ctx["unplanned_weights"]
    changeover_codes = ctx["changeover_codes"]

    defects = {
        ctx["p1"].id: [
            ("Weight Out-of-Limit",        "Tooling wear on punch face",         "IPC Check Station 1"),
            ("Hardness Failure",           "Insufficient compression force",     "In-process QC"),
            ("Dissolution Failure",        "Binder concentration deviation",     "QC Laboratory"),
            ("Appearance Defect",          "Coating solution viscosity high",    "100% Visual Inspection"),
            ("Content Uniformity Failure", "Blend segregation during transfer",  "IPC Check Station 2"),
            ("Disintegration Failure",     "Superdisintegrant level low",        "QC Laboratory"),
            ("Friability Failure",         "Excess compression speed",           "In-process QC"),
        ],
        ctx["p2"].id: [
            ("Weight Variance",         "Depositor timing drift",          "Inline Quality Check"),
            ("Colour Defect",           "Dye concentration variation",     "End-of-Line QC"),
            ("Moisture Content High",   "Cooling conveyor speed low",      "Sampling Station"),
            ("Packaging Seal Failure",  "Heat sealer temperature drop",    "End-of-Line QC"),
            ("Texture Anomaly",         "Baking temperature variance",     "Sampling Station"),
            ("Foreign Particle",        "Conveyor belt wear debris",       "End-of-Line QC"),
        ],
        ctx["p3"].id: [
            ("Purity Below Specification", "Raw material assay below CoA", "QC Lab Batch Release"),
            ("pH Out of Range",            "Neutralisation step incomplete","Online Analyzer"),
            ("Density Non-Conformance",    "Blend temperature excursion",  "In-process Sampling"),
            ("Moisture Content Elevated",  "Purging cycle duration short", "QC Lab Batch Release"),
            ("Colour Deviation",           "Contamination from previous batch","Online Analyzer"),
        ],
    }

    perf = {
        "changeover_per_line": {},
        "rejection_per_line":  {},
        "pareto_all":          {},
    }
    shifts_by_line = {ln.id: [] for ln in ctx["all_lines"]}
    batch_ctr = 0
    day0 = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    for day_off in range(HISTORY_DAYS, 0, -1):
        day_base   = day0 - timedelta(days=day_off)
        within_30  = day_off <= 30
        within_14  = day_off <= 14

        for line in ctx["all_lines"]:
            pid      = line.plant_id
            ml       = ctx["machines_by_line"][line.id]
            sup_list = ctx["sups"][pid]
            op_list  = ctx["ops"][pid]
            loggers  = op_list + sup_list
            sku_list = ctx["skus_by_plant"][pid]

            for delta, label in SHIFT_OFFSETS:
                s_start = day_base + delta
                s_end   = s_start + timedelta(hours=line.shift_duration_hours)

                rv = _rng.random()
                if rv < 0.65:
                    profile = "good"
                elif rv < 0.90:
                    profile = "moderate"
                else:
                    profile = "poor"

                high_rej = (line.id == ctx["l_ccl2"].id and within_14)

                target = line.target_output_per_shift
                if profile == "good":
                    pct      = _rng.uniform(0.88, 1.00)
                    dt_cnt   = _rng.choice([0, 1, 1, 2])
                    dt_rng   = (10.0, 35.0)
                    rej_rate = _rng.uniform(0.003, 0.015)
                elif profile == "moderate":
                    pct      = _rng.uniform(0.73, 0.88)
                    dt_cnt   = _rng.choice([1, 2, 2, 3])
                    dt_rng   = (25.0, 65.0)
                    rej_rate = _rng.uniform(0.015, 0.030)
                else:
                    pct      = _rng.uniform(0.56, 0.73)
                    dt_cnt   = _rng.choice([2, 3, 3, 4])
                    dt_rng   = (40.0, 95.0)
                    rej_rate = _rng.uniform(0.030, 0.055)

                if high_rej:
                    rej_rate = _rng.uniform(0.028, 0.045)

                actual = max(int(target * pct), 1)
                sku    = _rng.choice(sku_list)
                sup    = _rng.choice(sup_list)

                shift = Shift(
                    line_id=line.id, shift_label=label,
                    start_time=s_start, end_time=s_end,
                    supervisor_id=sup.id, sku_id=sku.id,
                    target_units=target, actual_units=0,
                    rejection_count=0, total_downtime_minutes=0.0,
                    status="completed",
                    created_at=s_start + timedelta(minutes=2),
                )
                db.session.add(shift)
                db.session.flush()

                total_unplanned = 0.0
                for _ in range(dt_cnt):
                    dur    = round(_rng.uniform(*dt_rng), 1)
                    offset = _rng.randint(10, max(10, int(line.shift_duration_hours * 60 - dur - 5)))
                    dts    = s_start + timedelta(minutes=offset)
                    dte    = dts + timedelta(minutes=dur)
                    rc     = _rng.choices(uc, weights=uw, k=1)[0]
                    logger = _rng.choice(loggers)
                    db.session.add(DowntimeEvent(
                        machine_id=_rng.choice(ml).id, shift_id=shift.id,
                        event_type="unplanned", reason_code_id=rc.id,
                        start_time=dts, end_time=dte,
                        duration_minutes=dur, logged_by=logger.id,
                        is_resolved=True, notes=None,
                        created_at=dts + timedelta(minutes=1),
                    ))
                    total_unplanned += dur
                    if within_30:
                        perf["pareto_all"][rc.id] = perf["pareto_all"].get(rc.id, 0.0) + dur

                num_out = _rng.randint(3, 6)
                running = 0
                iv_min  = (line.shift_duration_hours * 60.0) / num_out
                for i in range(num_out):
                    if i < num_out - 1:
                        delta_q = int(actual * 0.05)
                        q = max(1, int(actual / num_out) + _rng.randint(-delta_q, delta_q))
                        remaining_slots = num_out - i - 1
                        q = min(q, actual - running - remaining_slots)
                    else:
                        q = actual - running
                    q = max(1, q)
                    running += q
                    lt = s_start + timedelta(minutes=iv_min * (i + 1) + _rng.uniform(-8, 8))
                    lt = min(lt, s_end - timedelta(minutes=2))
                    db.session.add(ProductionOutput(
                        shift_id=shift.id,
                        logged_by=_rng.choice(loggers).id,
                        quantity=q, cumulative_total=running,
                        logged_at=lt,
                    ))
                actual = running

                total_rejected = 0
                if _rng.random() < 0.80:
                    n_rej = _rng.choice([1,1,1,2]) if (profile=="poor" or high_rej) else _rng.choice([0,1,1])
                    dcat  = defects[pid]
                    for _ in range(n_rej):
                        qty_r  = _rng.randint(20, 90) if high_rej else (
                                 _rng.randint(8, 45) if profile != "good" else _rng.randint(3, 18))
                        d, cause, qcp = _rng.choice(dcat)
                        db.session.add(RejectionEvent(
                            shift_id=shift.id, sku_id=sku.id,
                            machine_id=_rng.choice(ml).id,
                            quantity_rejected=qty_r, defect_type=d,
                            probable_cause=cause, quality_check_point=qcp,
                            batch_reference=f"BTH-{s_start.strftime('%Y%m%d')}-{_rng.randint(1000,9999)}",
                            logged_by=_rng.choice(loggers).id,
                            created_at=s_start + timedelta(minutes=_rng.randint(60, 400)),
                        ))
                        total_rejected += qty_r
                    if within_14:
                        r = perf["rejection_per_line"].setdefault(line.id, {"units": 0, "rejected": 0})
                        r["units"]    += actual
                        r["rejected"] += total_rejected

                shift.actual_units         = actual
                shift.rejection_count      = total_rejected
                shift.total_downtime_minutes = total_unplanned
                db.session.flush()
                _oee_inline(shift, line.shift_duration_hours, line.planned_break_minutes)

                if within_30:
                    shifts_by_line[line.id].append(shift.id)

                batch_ctr += 1
                if batch_ctr % 40 == 0:
                    db.session.commit()

    db.session.commit()

    co_targets = [
        (ctx["l_tcla"], 8, (44.0, 62.0)),
        (ctx["l_bpl1"], 6, (46.0, 62.0)),
    ]
    for line, count, dur_rng in co_targets:
        eligible = shifts_by_line[line.id]
        picked   = _rng.sample(eligible, min(count, len(eligible)))
        ml       = ctx["machines_by_line"][line.id]
        sl       = ctx["sups"][line.plant_id]
        for sid in picked:
            dur    = round(_rng.uniform(*dur_rng), 1)
            co_rc  = _rng.choice(changeover_codes)
            sup    = _rng.choice(sl)
            sh_obj = Shift.query.get(sid)
            co_s   = sh_obj.start_time + timedelta(minutes=15)
            co_e   = co_s + timedelta(minutes=dur)
            db.session.add(DowntimeEvent(
                machine_id=_rng.choice(ml).id, shift_id=sid,
                event_type="changeover", reason_code_id=co_rc.id,
                start_time=co_s, end_time=co_e,
                duration_minutes=dur, logged_by=sup.id,
                is_resolved=True,
                created_at=co_s + timedelta(minutes=2),
            ))
            perf["changeover_per_line"].setdefault(line.id, []).append(dur)
    db.session.commit()
    return perf


def _build_active_shifts(ctx):
    active_start = _current_shift_start()
    h = active_start.hour
    label = "C" if h < 4 else ("A" if h < 12 else "B")

    default_defects = {
        ctx["p1"].id: ("Weight Out-of-Limit",   "Punch wear at station 12",        "IPC Check Station 1"),
        ctx["p2"].id: ("Weight Variance",        "Depositor timing drift",          "Inline Quality Check"),
        ctx["p3"].id: ("pH Out of Range",        "Neutralisation step incomplete",  "Online Analyzer"),
    }
    uc = ctx["unplanned_codes"]
    uw = ctx["unplanned_weights"]
    active_shifts = {}

    for line in ctx["all_lines"]:
        pid      = line.plant_id
        ml       = ctx["machines_by_line"][line.id]
        sup_list = ctx["sups"][pid]
        op_list  = ctx["ops"][pid]
        loggers  = op_list + sup_list
        sku_list = ctx["skus_by_plant"][pid]
        sku = _rng.choice(sku_list)
        sup = _rng.choice(sup_list)

        elapsed_min     = (NOW - active_start).total_seconds() / 60
        partial_pct     = min(elapsed_min / (line.shift_duration_hours * 60), 0.95)
        partial_actual  = max(int(line.target_output_per_shift * partial_pct * _rng.uniform(0.82, 0.96)), 1)
        partial_rejected = int(partial_actual * _rng.uniform(0.005, 0.020))

        shift = Shift(
            line_id=line.id, shift_label=label,
            start_time=active_start, end_time=None,
            supervisor_id=sup.id, sku_id=sku.id,
            target_units=line.target_output_per_shift,
            actual_units=partial_actual, rejection_count=partial_rejected,
            total_downtime_minutes=0.0, status="active",
            created_at=active_start + timedelta(minutes=2),
        )
        db.session.add(shift)
        db.session.flush()

        if elapsed_min > 60:
            closed_dur = round(_rng.uniform(12.0, 35.0), 1)
            rc_c = _rng.choices(uc, weights=uw, k=1)[0]
            dts  = active_start + timedelta(minutes=20)
            dte  = dts + timedelta(minutes=closed_dur)
            db.session.add(DowntimeEvent(
                machine_id=_rng.choice(ml).id, shift_id=shift.id,
                event_type="unplanned", reason_code_id=rc_c.id,
                start_time=dts, end_time=dte,
                duration_minutes=closed_dur,
                logged_by=_rng.choice(loggers).id,
                is_resolved=True,
                created_at=dts + timedelta(minutes=1),
            ))
            shift.total_downtime_minutes = closed_dur

        rc_o     = _rng.choices(uc, weights=uw, k=1)[0]
        open_s   = NOW - timedelta(minutes=_rng.randint(12, 35))
        db.session.add(DowntimeEvent(
            machine_id=_rng.choice(ml).id, shift_id=shift.id,
            event_type="unplanned", reason_code_id=rc_o.id,
            start_time=open_s, end_time=None, duration_minutes=None,
            logged_by=_rng.choice(loggers).id, is_resolved=False,
            created_at=open_s + timedelta(minutes=1),
        ))

        running  = 0
        num_out  = max(1, int(elapsed_min / 90))
        per_qty  = partial_actual // max(num_out, 1)
        for i in range(num_out):
            if i == num_out - 1:
                q = partial_actual - running
            else:
                delta_q = max(1, int(per_qty * 0.10))
                q = max(1, per_qty + _rng.randint(-delta_q, delta_q))
            q = max(1, q)
            running = min(running + q, partial_actual)
            lt = active_start + timedelta(minutes=90 * (i + 1))
            db.session.add(ProductionOutput(
                shift_id=shift.id,
                logged_by=_rng.choice(loggers).id,
                quantity=q, cumulative_total=running,
                logged_at=min(lt, NOW - timedelta(minutes=5)),
            ))
        shift.actual_units = running

        if partial_rejected > 0:
            dtype, cause, qcp = default_defects.get(pid, ("Defect", "Unknown", "QC Station"))
            db.session.add(RejectionEvent(
                shift_id=shift.id, sku_id=sku.id,
                machine_id=_rng.choice(ml).id,
                quantity_rejected=partial_rejected,
                defect_type=dtype, probable_cause=cause,
                quality_check_point=qcp,
                batch_reference=f"BTH-{TODAY.strftime('%Y%m%d')}-{_rng.randint(1000,9999)}",
                logged_by=_rng.choice(loggers).id,
                created_at=active_start + timedelta(minutes=max(1,int(elapsed_min*0.4))),
            ))

        db.session.flush()
        active_shifts[line.id] = shift
        calculate_oee(shift.id)

    return active_shifts


def _build_most_studies(ctx):
    p1, p2, p3 = ctx["p1"], ctx["p2"], ctx["p3"]
    machines = ctx["machines"]
    skus     = ctx["skus"]
    p1_ie1, p1_ie2 = ctx["p1_ie1"], ctx["p1_ie2"]
    p2_ie, p3_ie   = ctx["p2_ie"],  ctx["p3_ie"]

    def _elem(study_id, seq, name, method, idx, ai=False, conf=None, desc=None):
        tmu = calculate_element_tmu(method, idx)
        db.session.add(MostElement(
            study_id=study_id, element_name=name, sequence_order=seq,
            most_method=method, index_values=idx, element_tmu=tmu,
            ai_suggested=ai, ai_confidence=conf if ai else None,
            analyst_override=False, element_description=desc,
            created_at=_ago(days=45),
        ))

    def _study(name, mcode, sku_code, analyst, plant, status, study_days_ago,
               allowance=15.0, version=1, parent_id=None, ai_used=False,
               obs="direct_entry", shift_obs="B", op_rating=100.0,
               notes=None, pub_days_ago=None):
        m   = machines[mcode]
        sku = skus[sku_code] if sku_code else ctx["skus_by_plant"][plant.id][0]
        pub = _ago(days=pub_days_ago) if pub_days_ago and status == "published" else None
        s   = MostStudy(
            study_name=name, workstation_id=m.id, sku_id=sku.id,
            analyst_id=analyst.id, plant_id=plant.id, status=status,
            sample_size=_rng.randint(5, 15), allowance_percent=allowance,
            total_tmu=0.0, standard_time_sec=0.0, allowed_time_sec=0.0,
            study_date=_agodate(days=study_days_ago),
            shift_observed=shift_obs, observation_method=obs,
            operator_rating=op_rating, version=version,
            parent_study_id=parent_id, published_at=pub,
            ai_assistance_used=ai_used, notes=notes,
            created_at=_ago(days=study_days_ago + 1),
        )
        db.session.add(s)
        db.session.flush()
        return s

    s_tca001_v1 = _study("Rotary Tablet Press - Compression v1","TCA-001","PCT-500",
                          p1_ie1,p1,"archived",75,version=1,
                          notes="Initial study, archived after press speed upgrade.")
    _elem(s_tca001_v1.id,1,"Retrieve tablet batch from hopper",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":1,"A3":1})
    _elem(s_tca001_v1.id,2,"Position die in press",
          "controlled_move",{"A1":1,"B1":0,"G1":3,"M1":6,"X1":1,"I1":1,"A2":1})
    _elem(s_tca001_v1.id,3,"Initiate compression cycle",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":1,"tool_tmu":40})
    db.session.flush()
    calculate_standard_time(s_tca001_v1.id)

    s_tca001_v2 = _study("Rotary Tablet Press - Compression v2","TCA-001","PCT-500",
                          p1_ie1,p1,"published",28,version=2,parent_id=s_tca001_v1.id,
                          ai_used=True,pub_days_ago=27,
                          notes="Revised after press speed upgrade. AI suggested element 3.")
    _elem(s_tca001_v2.id,1,"Retrieve tablet batch from hopper",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":1,"A3":1})
    _elem(s_tca001_v2.id,2,"Inspect and position die",
          "controlled_move",{"A1":1,"B1":0,"G1":3,"M1":6,"X1":1,"I1":1,"A2":1})
    _elem(s_tca001_v2.id,3,"Initiate compression and collect sample",
          "tool_use",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":3,"A3":1,"tool_tmu":60},
          ai=True,conf=0.82,desc="AI-suggested revised element post speed upgrade")
    _elem(s_tca001_v2.id,4,"Transfer tablets to collection tray",
          "general_move",{"A1":3,"B1":0,"G1":1,"A2":3,"B2":0,"P1":1,"A3":1})
    db.session.flush()
    calculate_standard_time(s_tca001_v2.id)

    s_tca002 = _study("High-Speed Granulator - Wet Granulation","TCA-002","PCT-500",
                       p1_ie2,p1,"published",45,pub_days_ago=44)
    _elem(s_tca002.id,1,"Load API and excipients into granulator bowl",
          "general_move",{"A1":6,"B1":1,"G1":3,"A2":6,"B2":0,"P1":3,"A3":1})
    _elem(s_tca002.id,2,"Add binder solution via spray nozzle",
          "tool_use",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":3,"A3":1,"tool_tmu":80})
    _elem(s_tca002.id,3,"Activate granulator and monitor endpoint",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":10,"X1":1,"I1":3,"A2":1})
    _elem(s_tca002.id,4,"Discharge granules to dryer",
          "general_move",{"A1":3,"B1":1,"G1":3,"A2":6,"B2":0,"P1":3,"A3":1},
          ai=True,conf=0.51)
    db.session.flush()
    calculate_standard_time(s_tca002.id)

    s_tca003 = _study("Fluid Bed Dryer - Drying Operation Draft","TCA-003","MET-500T",
                       p1_ie1,p1,"draft",10,notes="Draft under IE review.")
    _elem(s_tca003.id,1,"Load wet granules into dryer bowl",
          "general_move",{"A1":6,"B1":1,"G1":6,"A2":6,"B2":0,"P1":3,"A3":1})
    _elem(s_tca003.id,2,"Set drying parameters on HMI",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":0,"tool_tmu":30})
    db.session.flush()
    calculate_standard_time(s_tca003.id)

    s_tca004 = _study("Tablet Coating - Film Coating Operation","TCA-004","AML-5T",
                       p1_ie2,p1,"published",22,pub_days_ago=21)
    _elem(s_tca004.id,1,"Load tablets into coating pan",
          "general_move",{"A1":6,"B1":1,"G1":3,"A2":6,"B2":0,"P1":3,"A3":1})
    _elem(s_tca004.id,2,"Spray coating solution",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":10,"X1":1,"I1":3,"A2":1})
    _elem(s_tca004.id,3,"Sample and inspect coating thickness",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":1})
    db.session.flush()
    calculate_standard_time(s_tca004.id)

    s_cfb001 = _study("Capsule Filling - Automatic Fill Operation","CFB-001","AMX-250C",
                       p1_ie1,p1,"published",40,pub_days_ago=38,ai_used=True,
                       notes="AI assisted element 2 index suggestions.")
    _elem(s_cfb001.id,1,"Set up capsule hopper and segregator",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":3,"A3":1})
    _elem(s_cfb001.id,2,"Initiate fill cycle and monitor",
          "tool_use",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":3,"A3":1,"tool_tmu":50},
          ai=True,conf=0.78)
    _elem(s_cfb001.id,3,"Check and eject filled capsules",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":1,"I1":1,"A2":1})
    _elem(s_cfb001.id,4,"Reject defective capsules",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":0},
          ai=True,conf=0.63)
    db.session.flush()
    calculate_standard_time(s_cfb001.id)

    s_cfb002 = _study("Capsule Polishing - Standard Operation","CFB-002","AMX-250C",
                       p1_ie2,p1,"published",55,pub_days_ago=54)
    _elem(s_cfb002.id,1,"Load capsules into polisher drum",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":1,"A3":1})
    _elem(s_cfb002.id,2,"Run polishing cycle",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":0,"I1":1,"A2":1})
    _elem(s_cfb002.id,3,"Discharge and transfer capsules",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":3,"A3":1})
    db.session.flush()
    calculate_standard_time(s_cfb002.id)

    # CFB-003 intentionally has only a draft study -> triggers standard_time_update opportunity
    s_cfb003 = _study("Capsule Inspection - Draft Study","CFB-003","OFX-200C",
                       p1_ie1,p1,"draft",8,notes="Draft in progress, not yet validated.")
    _elem(s_cfb003.id,1,"Position capsule under camera system",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":1})
    db.session.flush()
    calculate_standard_time(s_cfb003.id)

    s_bpc001 = _study("Blister Forming - Standard Blister Pack","BPC-001","PAN-40T",
                       p1_ie1,p1,"published",35,pub_days_ago=33)
    _elem(s_bpc001.id,1,"Feed film roll and align track",
          "general_move",{"A1":3,"B1":0,"G1":1,"A2":3,"B2":0,"P1":1,"A3":1})
    _elem(s_bpc001.id,2,"Form blisters and fill tablets",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":10,"X1":1,"I1":3,"A2":1})
    _elem(s_bpc001.id,3,"Seal lidding foil",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":0,"tool_tmu":40})
    _elem(s_bpc001.id,4,"Cut and stack blister strips",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":0})
    db.session.flush()
    calculate_standard_time(s_bpc001.id)

    s_bpc002_v1 = _study("Cartoning - Manual Feed Operation","BPC-002","PAN-40T",
                          p1_ie2,p1,"archived",90,version=1)
    _elem(s_bpc002_v1.id,1,"Open carton and insert blister strips",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":3,"A3":1})
    _elem(s_bpc002_v1.id,2,"Insert product leaflet",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":1})
    _elem(s_bpc002_v1.id,3,"Close and lock carton",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":0,"tool_tmu":20})
    db.session.flush()
    calculate_standard_time(s_bpc002_v1.id)

    s_bpc002_v2 = _study("Cartoning - Automated Feed v2","BPC-002","PAN-40T",
                          p1_ie1,p1,"under_revision",15,version=2,
                          parent_id=s_bpc002_v1.id,
                          notes="Under revision to capture new auto-erector cycle times.")
    _elem(s_bpc002_v2.id,1,"Load blister strips into auto-feeder",
          "general_move",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":1,"A3":1})
    _elem(s_bpc002_v2.id,2,"Monitor cartoning machine cycle",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":1,"I1":1,"A2":1})
    db.session.flush()
    calculate_standard_time(s_bpc002_v2.id)

    s_bpc003 = _study("Shrink Wrap - Overwrap Operation","BPC-003","IBP-400T",
                       p1_ie2,p1,"published",50,pub_days_ago=48)
    _elem(s_bpc003.id,1,"Feed cartons onto shrink conveyor",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":1})
    _elem(s_bpc003.id,2,"Apply shrink film and pass through tunnel",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":0,"I1":1,"A2":1})
    _elem(s_bpc003.id,3,"Inspect and stack finished packs",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":0})
    db.session.flush()
    calculate_standard_time(s_bpc003.id)

    s_bpl001 = _study("Biscuit Baking - Oven Operation","BPL-001","BCT-CHOC",
                       p2_ie,p2,"published",50,pub_days_ago=48)
    _elem(s_bpl001.id,1,"Load dough onto oven band",
          "general_move",{"A1":6,"B1":1,"G1":3,"A2":6,"B2":0,"P1":3,"A3":1})
    _elem(s_bpl001.id,2,"Monitor baking zone temperatures",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":3,"X1":1,"I1":1,"A2":1})
    _elem(s_bpl001.id,3,"Discharge biscuits to cooling conveyor",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":1,"A3":1})
    db.session.flush()
    calculate_standard_time(s_bpl001.id)

    s_bpl002 = _study("Cooling Conveyor - Product Cooling","BPL-002","BCT-CREAM",
                       p2_ie,p2,"published",25,pub_days_ago=23)
    _elem(s_bpl002.id,1,"Inspect biscuits on cooling conveyor",
          "general_move",{"A1":1,"B1":1,"G1":1,"A2":1,"B2":0,"P1":1,"A3":1})
    _elem(s_bpl002.id,2,"Remove and reject defective biscuits",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":0},
          ai=True,conf=0.46)
    db.session.flush()
    calculate_standard_time(s_bpl002.id)

    s_bpl003 = _study("Cream Sandwiching - Sandwich Assembly","BPL-003","BCT-CREAM",
                       p2_ie,p2,"published",32,pub_days_ago=30)
    _elem(s_bpl003.id,1,"Load biscuit base onto sandwicher",
          "general_move",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":1,"A3":1})
    _elem(s_bpl003.id,2,"Deposit cream and apply top biscuit",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":0,"tool_tmu":30})
    _elem(s_bpl003.id,3,"Inspect and convey sandwich biscuit",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":3,"X1":1,"I1":1,"A2":1})
    db.session.flush()
    calculate_standard_time(s_bpl003.id)

    s_ccl001 = _study("Chocolate Enrobing - Enrobing Operation","CCL-001","CCF-MILK",
                       p2_ie,p2,"published",40,pub_days_ago=38)
    _elem(s_ccl001.id,1,"Feed wafers onto enrober wire belt",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":1,"A3":1})
    _elem(s_ccl001.id,2,"Monitor chocolate temper and flow rate",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":1,"I1":3,"A2":1})
    _elem(s_ccl001.id,3,"Transfer enrobed wafers to cooling tunnel",
          "general_move",{"A1":1,"B1":0,"G1":1,"A2":3,"B2":0,"P1":1,"A3":1})
    db.session.flush()
    calculate_standard_time(s_ccl001.id)

    # CCL-002 intentionally only draft -> triggers standard_time_update opportunity
    s_ccl002 = _study("Cooling Tunnel - Initial Draft","CCL-002","CCF-MILK",
                       p2_ie,p2,"draft",5)
    _elem(s_ccl002.id,1,"Monitor cooling zone temperatures",
          "general_move",{"A1":1,"B1":1,"G1":1,"A2":1,"B2":0,"P1":1,"A3":1})
    db.session.flush()
    calculate_standard_time(s_ccl002.id)

    s_ccl003 = _study("Packaging - Primary Pack Operation","CCL-003","CCF-DARK",
                       p2_ie,p2,"published",45,pub_days_ago=43)
    _elem(s_ccl003.id,1,"Load product into packaging feeder",
          "general_move",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":1,"A3":1})
    _elem(s_ccl003.id,2,"Form and fill pouch",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":0,"tool_tmu":50})
    _elem(s_ccl003.id,3,"Seal and cut pouch",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":1,"I1":1,"A2":1})
    db.session.flush()
    calculate_standard_time(s_ccl003.id)

    # CBA-001 published 95 days ago -> older than 90-day cutoff -> triggers standard_time_update
    s_cba001 = _study("Batch Reactor - Chemical Blending Operation","CBA-001","IPA-99",
                       p3_ie,p3,"published",95,pub_days_ago=93,
                       notes="Study date >90 days ago — will trigger standard-time-gap opportunity.")
    _elem(s_cba001.id,1,"Load raw material into reactor via pump",
          "general_move",{"A1":6,"B1":0,"G1":3,"A2":6,"B2":0,"P1":3,"A3":1})
    _elem(s_cba001.id,2,"Set agitation speed and temperature",
          "tool_use",{"A1":1,"B1":0,"G1":1,"A2":1,"B2":0,"P1":3,"A3":0,"tool_tmu":30})
    _elem(s_cba001.id,3,"Monitor reaction progress and take sample",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":10,"X1":1,"I1":3,"A2":1})
    db.session.flush()
    calculate_standard_time(s_cba001.id)

    s_cba002 = _study("Centrifugal Pump - Transfer Operation","CBA-002","IPA-99",
                       p3_ie,p3,"published",60,pub_days_ago=58)
    _elem(s_cba002.id,1,"Connect transfer hose and prime pump",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":3,"A3":1})
    _elem(s_cba002.id,2,"Operate pump transfer and monitor flow",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":6,"X1":1,"I1":3,"A2":1})
    _elem(s_cba002.id,3,"Disconnect and rinse transfer hose",
          "general_move",{"A1":3,"B1":0,"G1":3,"A2":3,"B2":0,"P1":1,"A3":1})
    db.session.flush()
    calculate_standard_time(s_cba002.id)

    # DFB-001 has no study at all -> triggers standard_time_update opportunity

    s_dfb002 = _study("Drum Filling - IPA Drum Filling Operation","DFB-002","IPA-99",
                       p3_ie,p3,"published",70,pub_days_ago=68)
    _elem(s_dfb002.id,1,"Position empty drum on weigh scale",
          "general_move",{"A1":3,"B1":1,"G1":3,"A2":3,"B2":0,"P1":3,"A3":1})
    _elem(s_dfb002.id,2,"Connect fill nozzle to drum bung",
          "general_move",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":3,"A3":1})
    _elem(s_dfb002.id,3,"Fill drum and monitor weight setpoint",
          "controlled_move",{"A1":1,"B1":0,"G1":1,"M1":10,"X1":1,"I1":3,"A2":1})
    _elem(s_dfb002.id,4,"Disconnect, seal and label drum",
          "tool_use",{"A1":1,"B1":0,"G1":3,"A2":1,"B2":0,"P1":3,"A3":1,"tool_tmu":60},
          ai=True,conf=0.55)
    db.session.flush()
    calculate_standard_time(s_dfb002.id)


def _build_alert_rules(ctx):
    p1, p2, p3 = ctx["p1"], ctx["p2"], ctx["p3"]
    rules_def = [
        dict(plant_id=p1.id, rule_name="High Rejection Rate - Pharma Excel",
             metric_name="rejection_rate", operator="gt", threshold_value=3.0,
             time_window_minutes=480, line_id=None,
             recipient_user_ids=[ctx["p1_qa"].id, ctx["p1_pm"].id],
             escalation_user_ids=[ctx["p1_pm"].id],
             escalation_timeout_minutes=90, created_by=ctx["p1_pm"].id),
        dict(plant_id=p1.id, rule_name="Unplanned Downtime Alert - Line A",
             metric_name="downtime_duration", operator="gt", threshold_value=45.0,
             time_window_minutes=480, line_id=ctx["l_tcla"].id,
             recipient_user_ids=[ctx["p1_ie1"].id, ctx["p1_pm"].id],
             escalation_user_ids=[ctx["p1_pm"].id],
             escalation_timeout_minutes=60, created_by=ctx["p1_pm"].id),
        dict(plant_id=p1.id, rule_name="OEE Drop Alert - Capsule Filling Line B",
             metric_name="oee_percent", operator="lt", threshold_value=65.0,
             time_window_minutes=60, line_id=ctx["l_cflb"].id,
             recipient_user_ids=[ctx["p1_ie1"].id, ctx["p1_qa"].id],
             escalation_user_ids=[ctx["p1_pm"].id],
             escalation_timeout_minutes=120, created_by=ctx["p1_ie1"].id),
        dict(plant_id=p2.id, rule_name="Rejection Rate Spike - NutriCraft",
             metric_name="rejection_rate", operator="gt", threshold_value=2.5,
             time_window_minutes=480, line_id=None,
             recipient_user_ids=[ctx["p2_qa"].id, ctx["p2_pm"].id],
             escalation_user_ids=[ctx["p2_pm"].id],
             escalation_timeout_minutes=90, created_by=ctx["p2_pm"].id),
        dict(plant_id=p2.id, rule_name="Output Attainment Low - Biscuit Line 1",
             metric_name="output_attainment", operator="lt", threshold_value=75.0,
             time_window_minutes=240, line_id=ctx["l_bpl1"].id,
             recipient_user_ids=[ctx["p2_ie"].id, ctx["p2_pm"].id],
             escalation_user_ids=[ctx["p2_pm"].id],
             escalation_timeout_minutes=60, created_by=ctx["p2_ie"].id),
        dict(plant_id=p2.id, rule_name="Downtime Alert - Confectionery Line 2",
             metric_name="downtime_duration", operator="gt", threshold_value=40.0,
             time_window_minutes=480, line_id=ctx["l_ccl2"].id,
             recipient_user_ids=[ctx["p2_qa"].id, ctx["p2_ie"].id],
             escalation_user_ids=[ctx["p2_pm"].id],
             escalation_timeout_minutes=90, created_by=ctx["p2_pm"].id),
        dict(plant_id=p3.id, rule_name="Process Downtime Alert - ChemFlow",
             metric_name="downtime_duration", operator="gt", threshold_value=60.0,
             time_window_minutes=480, line_id=None,
             recipient_user_ids=[ctx["p3_pm"].id, ctx["p3_qa"].id],
             escalation_user_ids=[ctx["p3_pm"].id],
             escalation_timeout_minutes=120, created_by=ctx["p3_pm"].id),
        dict(plant_id=p3.id, rule_name="OEE Alert - Chemical Blending Line Alpha",
             metric_name="oee_percent", operator="lt", threshold_value=60.0,
             time_window_minutes=60, line_id=ctx["l_cbla"].id,
             recipient_user_ids=[ctx["p3_qa"].id, ctx["p3_pm"].id],
             escalation_user_ids=[ctx["p3_pm"].id],
             escalation_timeout_minutes=90, created_by=ctx["p3_pm"].id),
    ]
    rules = []
    for rd in rules_def:
        r = AlertRule(is_active=True, created_at=_ago(days=55), **rd)
        db.session.add(r)
        rules.append(r)
    db.session.flush()
    db.session.commit()
    return rules


def _build_alert_events(ctx, rules, active_shifts):
    ae1 = AlertEvent(
        rule_id=rules[0].id, plant_id=ctx["p1"].id, line_id=None,
        triggered_at=_ago(days=42), triggered_value=3.8, threshold_value=3.0,
        status="acknowledged", acknowledged_by=ctx["p1_qa"].id,
        acknowledged_at=_ago(days=42, hours=-1),
        action_taken="capa_raised", capa_id=None,
        notes="Rejection rate 3.8% on Tablet Compression Line A during Shift C.",
        created_at=_ago(days=42),
    )
    ae2 = AlertEvent(
        rule_id=rules[1].id, plant_id=ctx["p1"].id, line_id=ctx["l_tcla"].id,
        triggered_at=_ago(days=25), triggered_value=52.0, threshold_value=45.0,
        status="acknowledged", acknowledged_by=ctx["p1_ie1"].id,
        acknowledged_at=_ago(days=25, hours=-2),
        action_taken="investigate",
        notes="Bearing failure on TCA-001 caused 52 min unplanned downtime.",
        created_at=_ago(days=25),
    )
    ae3 = AlertEvent(
        rule_id=rules[2].id, plant_id=ctx["p1"].id, line_id=ctx["l_cflb"].id,
        triggered_at=_ago(days=18), triggered_value=62.4, threshold_value=65.0,
        status="dismissed", acknowledged_by=ctx["p1_pm"].id,
        acknowledged_at=_ago(days=18, hours=-1),
        action_taken="dismissed_reason",
        notes="OEE dip attributed to planned changeover. No action required.",
        created_at=_ago(days=18),
    )
    ae4 = AlertEvent(
        rule_id=rules[3].id, plant_id=ctx["p2"].id, line_id=None,
        triggered_at=_ago(days=35), triggered_value=3.1, threshold_value=2.5,
        status="acknowledged", acknowledged_by=ctx["p2_qa"].id,
        acknowledged_at=_ago(days=35, hours=-1),
        action_taken="capa_raised", capa_id=None,
        notes="Rejection rate 3.1% on Confectionery Coating Line 2, last 8 hours.",
        created_at=_ago(days=35),
    )
    ae5 = AlertEvent(
        rule_id=rules[4].id, plant_id=ctx["p2"].id, line_id=ctx["l_bpl1"].id,
        triggered_at=_ago(days=12), triggered_value=72.4, threshold_value=75.0,
        status="acknowledged", acknowledged_by=ctx["p2_ie"].id,
        acknowledged_at=_ago(days=12, hours=-1),
        action_taken="investigate",
        notes="Biscuit line output attainment 72.4%. Oven temperature variance under investigation.",
        created_at=_ago(days=12),
    )
    ae6 = AlertEvent(
        rule_id=rules[5].id, plant_id=ctx["p2"].id, line_id=ctx["l_ccl2"].id,
        triggered_at=_ago(hours=2), triggered_value=47.5, threshold_value=40.0,
        status="open", acknowledged_by=None, acknowledged_at=None,
        action_taken=None, notes=None,
        created_at=_ago(hours=2),
    )
    ae7 = AlertEvent(
        rule_id=rules[2].id, plant_id=ctx["p1"].id, line_id=ctx["l_cflb"].id,
        triggered_at=_ago(hours=3), triggered_value=63.1, threshold_value=65.0,
        status="escalated", acknowledged_by=None, acknowledged_at=None,
        action_taken=None, escalated_at=_ago(hours=1),
        notes=None,
        created_at=_ago(hours=3),
    )
    ae8 = AlertEvent(
        rule_id=rules[6].id, plant_id=ctx["p3"].id, line_id=None,
        triggered_at=_ago(days=20), triggered_value=68.0, threshold_value=60.0,
        status="acknowledged", acknowledged_by=ctx["p3_pm"].id,
        acknowledged_at=_ago(days=20, hours=-2),
        action_taken="investigate",
        notes="Reactor jacket cooling failure caused extended downtime on CBL-A.",
        created_at=_ago(days=20),
    )

    db.session.add_all([ae1, ae2, ae3, ae4, ae5, ae6, ae7, ae8])
    db.session.flush()
    db.session.commit()
    return [("p1_rej", ae1), ("p2_rej", ae4)]


def _build_capas(ctx, evts_for_capa):
    machines = ctx["machines"]
    skus     = ctx["skus"]
    ae_p1    = next(ae for k, ae in evts_for_capa if k == "p1_rej")
    ae_p2    = next(ae for k, ae in evts_for_capa if k == "p2_rej")

    seq = {2025: 0, 2026: 0}
    def _cnum(y):
        seq[y] += 1
        return f"CAPA-{y}-{seq[y]:04d}"

    c25_01 = CapaRecord(
        capa_number=_cnum(2025),
        title="Tablet Weight Variability - Batch B25001",
        severity="major", source_type="deviation",
        source_description="IPC weight check exceeded AQL limits on 3 consecutive samples.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["TCA-001"].id,
        affected_sku_id=skus["PCT-500"].id, affected_batch="BTH-2025-0042",
        deviation_description="In-process weight check on Batch B25001 showed 4 samples outside "
            "+-5% of mean. SOP deviation requires immediate investigation and batch quarantine.",
        immediate_action="Batch quarantined. Line stopped for punch inspection.",
        root_cause_summary="Worn lower punch cup causing weight variation.",
        corrective_action="All punch sets replaced. Compression force recalibrated.",
        preventive_action="Punch wear inspection frequency increased from monthly to bi-weekly.",
        owner_id=ctx["p1_qa"].id, raised_by_id=ctx["p1_sup1"].id,
        reviewer_id=ctx["p1_pm"].id, status="closed", priority="high",
        due_date=_agodate(days=120), closed_at=_ago(days=115),
        closure_notes="Root cause confirmed as punch wear. Replacement completed. "
            "Batch destroyed per SOP. New inspection frequency validated over 30 days.",
        effectiveness_verified=True, effectiveness_date=_agodate(days=85),
        evidence_paths=["evidence/CAPA-2025-0001-punch-replacement.pdf",
                        "evidence/CAPA-2025-0001-compression-log.xlsx"],
        created_at=_ago(days=150),
    )
    c25_02 = CapaRecord(
        capa_number=_cnum(2025),
        title="Capsule Fill Weight OOS - Amoxicillin 250mg",
        severity="critical", source_type="audit",
        source_description="External GMP audit finding AF-2025-012.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["CFB-001"].id,
        affected_sku_id=skus["AMX-250C"].id,
        deviation_description="Quarterly GMP audit found 8 capsule fill weight samples in 2025 "
            "outside +-7.5% tolerance with no documented investigation.",
        immediate_action="Historical batches reviewed. Two batches quarantined for retesting.",
        root_cause_summary="Dosing disc worn beyond tolerance limit.",
        corrective_action="Dosing disc replaced. Weight check frequency doubled for 60 days.",
        preventive_action="Dosing disc added to planned maintenance schedule at 90-day interval.",
        owner_id=ctx["p1_qa"].id, raised_by_id=ctx["p1_pm"].id,
        reviewer_id=None, status="closed", priority="high",
        due_date=_agodate(days=100), closed_at=_ago(days=95),
        closure_notes="Dosing disc replaced and validated. 60-day enhanced monitoring completed "
            "with all results in specification. Maintenance schedule updated.",
        effectiveness_verified=True, effectiveness_date=_agodate(days=35),
        evidence_paths=["evidence/CAPA-2025-0002-disc-replacement.pdf",
                        "evidence/CAPA-2025-0002-verification-data.xlsx"],
        created_at=_ago(days=140),
    )
    c25_03 = CapaRecord(
        capa_number=_cnum(2025),
        title="Blister Seal Integrity Failure - Pantoprazole 40mg",
        severity="major", source_type="customer_complaint",
        source_description="Distributor reported customer complaints of open blisters.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["BPC-001"].id,
        affected_sku_id=skus["PAN-40T"].id,
        deviation_description="Three customer complaints received regarding blister seal failure. "
            "Inadequate heat seal confirmed on Batch BTH-20251108.",
        immediate_action="Field market withdrawal initiated. QA hold placed on batch.",
        root_cause_summary="Sealing station heat element degraded, causing intermittent low-temperature seals.",
        corrective_action="Heat element replaced. Temperature validation performed.",
        preventive_action="Heat element added to weekly PM checklist with temperature verification.",
        owner_id=ctx["p1_qa"].id, raised_by_id=ctx["p1_pm"].id,
        reviewer_id=ctx["p1_pm"].id, status="closed", priority="high",
        due_date=_agodate(days=80), closed_at=_ago(days=70),
        closure_notes="Heat element replaced and validated. Market withdrawal completed per SOP-QA-028.",
        evidence_paths=["evidence/CAPA-2025-0003-validation-report.pdf"],
        effectiveness_verified=True, effectiveness_date=_agodate(days=40),
        created_at=_ago(days=130),
    )
    c25_04 = CapaRecord(
        capa_number=_cnum(2025),
        title="Biscuit Moisture Content Excursion - BCT-CREAM",
        severity="minor", source_type="deviation",
        source_description="In-line NIR moisture analyser detected out-of-spec reading during Shift B.",
        plant_id=ctx["p2"].id, affected_machine_id=machines["BPL-001"].id,
        affected_sku_id=skus["BCT-CREAM"].id,
        deviation_description="NIR moisture reading 4.2% detected against specification 2.5-3.5%. "
            "Four production batches held pending investigation.",
        immediate_action="Oven temperature setpoints reviewed and corrected.",
        root_cause_summary="Thermocouple drift in oven zone 3 caused temperature underrun.",
        corrective_action="Thermocouple replaced and oven revalidated.",
        preventive_action="Thermocouple calibration frequency increased to bi-monthly.",
        owner_id=ctx["p2_qa"].id, raised_by_id=ctx["p2_sup1"].id,
        reviewer_id=ctx["p2_pm"].id, status="closed", priority="medium",
        due_date=_agodate(days=85), closed_at=_ago(days=80),
        closure_notes="Thermocouple replaced. Oven revalidated with 5-day monitoring. "
            "All held batches tested and conform to specification.",
        evidence_paths=["evidence/CAPA-2025-0004-oven-validation.pdf"],
        effectiveness_verified=True, effectiveness_date=_agodate(days=50),
        created_at=_ago(days=120),
    )
    c25_05 = CapaRecord(
        capa_number=_cnum(2025),
        title="IPA Purity Below CoA - Batch IPA-25-0072",
        severity="major", source_type="deviation",
        source_description="QC release testing showed purity 98.1% against spec minimum 99.0%.",
        plant_id=ctx["p3"].id, affected_machine_id=machines["CBA-001"].id,
        affected_sku_id=skus["IPA-99"].id,
        deviation_description="Batch IPA-25-0072 purity 98.1%, below minimum 99.0%. "
            "Supplier CoA claimed 99.2% purity.",
        immediate_action="Batch rejected and quarantined. Supplier notified.",
        root_cause_summary="Raw material supplier CoA was inaccurate. No incoming QC verification performed.",
        corrective_action="Incoming raw material QC protocol implemented.",
        preventive_action="Supplier qualification review initiated.",
        owner_id=ctx["p3_qa"].id, raised_by_id=ctx["p3_pm"].id,
        reviewer_id=None, status="closed", priority="high",
        due_date=_agodate(days=75), closed_at=_ago(days=68),
        closure_notes="Incoming QC protocol implemented and validated. Batch destroyed. "
            "Supplier placed on probationary status.",
        evidence_paths=["evidence/CAPA-2025-0005-incoming-qc-procedure.pdf",
                        "evidence/CAPA-2025-0005-supplier-audit-report.pdf"],
        effectiveness_verified=True, effectiveness_date=_agodate(days=38),
        created_at=_ago(days=110),
    )
    c25_06 = CapaRecord(
        capa_number=_cnum(2025),
        title="Recurring Bearing Failure - TCA-001 Rotary Tablet Press",
        severity="major", source_type="self_initiated",
        source_description="Pattern of recurring EF-MF-01 bearing failures identified in downtime analysis.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["TCA-001"].id,
        deviation_description="Analysis of downtime data shows EF-MF-01 (Bearing Failure) "
            "in 34% of unplanned downtime events on TCL-A over 60 days. "
            "Root cause investigation required to break the pattern.",
        immediate_action="Increased lubrication frequency. Bearing stock levels reviewed.",
        owner_id=ctx["p1_ie1"].id, raised_by_id=ctx["p1_pm"].id,
        reviewer_id=ctx["p1_pm"].id, status="overdue", priority="medium",
        due_date=_agodate(days=5),
        created_at=_ago(days=45),
    )
    c25_07 = CapaRecord(
        capa_number=_cnum(2025),
        title="Chocolate Enrober Downtime Spike - CCL-001",
        severity="minor", source_type="deviation",
        source_description="Multiple unplanned downtime events on CCL-001 in October 2025.",
        plant_id=ctx["p2"].id, affected_machine_id=machines["CCL-001"].id,
        affected_sku_id=skus["CCF-MILK"].id,
        deviation_description="Enrober CCL-001 recorded 4 unplanned downtime events totalling 175 min "
            "in October 2025, against target of under 60 min per month.",
        immediate_action="Pump seals inspected and tightened. Chocolate viscosity rechecked.",
        owner_id=ctx["p2_qa"].id, raised_by_id=ctx["p2_sup2"].id,
        reviewer_id=None, status="overdue", priority="low",
        due_date=_agodate(days=15),
        created_at=_ago(days=55),
    )
    c25_08 = CapaRecord(
        capa_number=_cnum(2025),
        title="Reactor CIP Validation Gap - CBA-001",
        severity="minor", source_type="audit",
        source_description="Internal audit found CIP validation records not completed for Q3 2025.",
        plant_id=ctx["p3"].id, affected_machine_id=machines["CBA-001"].id,
        deviation_description="Internal audit IA-2025-Q3 found CIP validation for CBA-001 not completed "
            "for three batches in Q3 2025 due to validation system unavailability.",
        immediate_action="CIP validation performed retrospectively. Records submitted.",
        owner_id=ctx["p3_qa"].id, raised_by_id=ctx["p3_pm"].id,
        reviewer_id=None, status="overdue", priority="medium",
        due_date=_agodate(days=3),
        created_at=_ago(days=40),
    )

    c26_01 = CapaRecord(
        capa_number=_cnum(2026),
        title="Amlodipine 5mg Weight OOS - Batch AML-26-0012",
        severity="major", source_type="deviation",
        source_description="IPC weight check failed during Shift A on Tablet Compression Line A.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["TCA-001"].id,
        affected_sku_id=skus["AML-5T"].id, affected_batch="AML-26-0012",
        deviation_description="Three consecutive IPC weight samples exceeded upper limit of 110% "
            "label claim during compression Shift A. Batch quarantined.",
        immediate_action="Line stopped. Batch quarantined. Compression force reduced by 5%.",
        owner_id=ctx["p1_qa"].id, raised_by_id=ctx["p1_sup1"].id,
        reviewer_id=ctx["p1_pm"].id, status="in_progress", priority="high",
        due_date=_agodate(days=-14),
        created_at=_ago(days=30),
    )
    c26_02 = CapaRecord(
        capa_number=_cnum(2026),
        title="Granulator Blade Failure - TCA-002",
        severity="major", source_type="deviation",
        source_description="Granulator blade assembly found cracked during Shift B cleaning inspection.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["TCA-002"].id,
        deviation_description="Post-shift cleaning inspection revealed cracked impeller blade on TCA-002. "
            "Risk of metal contamination in granulate. Batch quarantined for testing.",
        immediate_action="Granulator taken out of service. Blade replaced. Batch sent for metal particle testing.",
        root_cause_summary="Fatigue crack from impact during previous changeover.",
        corrective_action="New blade installed and validated. Impact protection guard added.",
        preventive_action="Blade visual inspection added to pre-shift checklist.",
        owner_id=ctx["p1_ie1"].id, raised_by_id=ctx["p1_qa"].id,
        reviewer_id=ctx["p1_pm"].id, status="pending_review", priority="high",
        due_date=_agodate(days=-7),
        created_at=_ago(days=22),
    )
    c26_03 = CapaRecord(
        capa_number=_cnum(2026),
        title="Elevated Rejection Rate - Tablet Compression Shift C",
        severity="major", source_type="alert", source_id=ae_p1.id,
        source_description=f"AlertEvent #{ae_p1.id}: rejection_rate triggered at 3.8% (threshold 3.0%).",
        plant_id=ctx["p1"].id, affected_machine_id=machines["TCA-001"].id,
        deviation_description="Alert triggered for rejection rate 3.8% on Tablet Compression Line A "
            "during Shift C. 145 tablets rejected from 3,820-unit output.",
        immediate_action="Punch set inspected. Four worn punches replaced. Line restarted.",
        root_cause_summary="Punch set worn past specification tolerance.",
        corrective_action="Complete punch set replaced. IPC frequency increased to every 30 minutes.",
        preventive_action="Punch change interval reduced from 4 weeks to 3 weeks.",
        owner_id=ctx["p1_qa"].id, raised_by_id=ctx["p1_ie1"].id,
        reviewer_id=ctx["p1_pm"].id, status="closed", priority="high",
        due_date=_agodate(days=10), closed_at=_ago(days=30),
        closure_notes="Punch set replaced and validated. Enhanced 30-day monitoring cycle completed "
            "with rejection rate at 0.9%. CAPA effective.",
        effectiveness_verified=True, effectiveness_date=_agodate(days=12),
        evidence_paths=["evidence/CAPA-2026-0003-punch-replacement.pdf",
                        "evidence/CAPA-2026-0003-ipc-monitoring.xlsx"],
        created_at=_ago(days=42),
    )
    c26_04 = CapaRecord(
        capa_number=_cnum(2026),
        title="Capsule Polisher Jam - CFB-002",
        severity="minor", source_type="deviation",
        source_description="Polisher drum jammed twice during Shift B, causing 38 min downtime.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["CFB-002"].id,
        deviation_description="Capsule polisher CFB-002 jammed twice during Shift B due to capsule "
            "bridging at drum inlet. Total 38 minutes unplanned downtime.",
        immediate_action="Drum cleared. Feed rate reduced.",
        owner_id=ctx["p1_ie2"].id, raised_by_id=ctx["p1_sup2"].id,
        reviewer_id=None, status="open", priority="low",
        due_date=_agodate(days=-21),
        created_at=_ago(days=8),
    )
    c26_05 = CapaRecord(
        capa_number=_cnum(2026),
        title="Biscuit Cream Overfill - BCT-CREAM Line 1",
        severity="minor", source_type="deviation",
        source_description="Cream depositor intermittently overfilling biscuit sandwiches by 8-12%.",
        plant_id=ctx["p2"].id, affected_machine_id=machines["BPL-003"].id,
        affected_sku_id=skus["BCT-CREAM"].id,
        deviation_description="Cream sandwicher BPL-003 depositor overfilling BCT-CREAM packs by 8-12%. "
            "Interim weight monitoring implemented.",
        immediate_action="Depositor recalibrated. Weight monitoring every 15 min implemented.",
        owner_id=ctx["p2_qa"].id, raised_by_id=ctx["p2_sup1"].id,
        reviewer_id=ctx["p2_pm"].id, status="in_progress", priority="medium",
        due_date=_agodate(days=-10),
        created_at=_ago(days=18),
    )
    c26_06 = CapaRecord(
        capa_number=_cnum(2026),
        title="Chocolate Rejection Rate >2.5% - CCL-2",
        severity="major", source_type="alert", source_id=ae_p2.id,
        source_description=f"AlertEvent #{ae_p2.id}: rejection_rate triggered at 3.1% (threshold 2.5%).",
        plant_id=ctx["p2"].id, affected_machine_id=machines["CCL-001"].id,
        affected_sku_id=skus["CCF-MILK"].id,
        deviation_description="Alert triggered for rejection rate 3.1% on CCL-2. "
            "Primary defect: colour deviation on milk chocolate enrobed wafers.",
        immediate_action="Chocolate temper rechecked. Temperature setpoint raised by 0.5 degrees C.",
        root_cause_summary="Chocolate tempering temperature below optimal range due to ambient temperature rise.",
        corrective_action="Tempering setpoint adjusted. Seasonal ambient temperature compensation procedure written.",
        preventive_action="Temperature compensation SOP implemented and operators trained.",
        owner_id=ctx["p2_qa"].id, raised_by_id=ctx["p2_ie"].id,
        reviewer_id=ctx["p2_pm"].id, status="closed", priority="high",
        due_date=_agodate(days=5), closed_at=_ago(days=28),
        closure_notes="Tempering SOP implemented. 14-day monitoring showed rejection rate at 1.2%. CAPA effective.",
        effectiveness_verified=True, effectiveness_date=_agodate(days=14),
        evidence_paths=["evidence/CAPA-2026-0006-temper-procedure.pdf",
                        "evidence/CAPA-2026-0006-rejection-trend.xlsx"],
        created_at=_ago(days=35),
    )
    c26_07 = CapaRecord(
        capa_number=_cnum(2026),
        title="Cooling Tunnel Temperature Drift - CCL-002",
        severity="minor", source_type="deviation",
        source_description="Online temperature sensor showing +-2 degrees C drift during Shift A.",
        plant_id=ctx["p2"].id, affected_machine_id=machines["CCL-002"].id,
        deviation_description="Cooling tunnel CCL-002 temperature drifting +-2 degrees C from setpoint "
            "during first hour of Shift A. Product texture anomalies reported downstream.",
        immediate_action="Product batch held. Temperature sensor checked.",
        owner_id=ctx["p2_qa"].id, raised_by_id=ctx["p2_sup2"].id,
        reviewer_id=None, status="overdue", priority="medium",
        due_date=_agodate(days=2),
        created_at=_ago(days=12),
    )
    c26_08 = CapaRecord(
        capa_number=_cnum(2026),
        title="Reactor pH Excursion - Batch IPA-26-0018",
        severity="major", source_type="deviation",
        source_description="Online pH analyser reading 6.2 against target 6.8-7.2 during blending.",
        plant_id=ctx["p3"].id, affected_machine_id=machines["CBA-001"].id,
        affected_sku_id=skus["IPA-99"].id,
        deviation_description="pH excursion on Batch IPA-26-0018 during neutralisation step. "
            "pH 6.2 below specification minimum 6.8.",
        immediate_action="Blending stopped. NaOH addition performed under QA supervision. Re-analysis submitted.",
        root_cause_summary="NaOH dosing pump calibration drift caused under-dosing.",
        corrective_action="NaOH dosing pump recalibrated and validated.",
        preventive_action="Pump calibration frequency increased to weekly.",
        owner_id=ctx["p3_qa"].id, raised_by_id=ctx["p3_sup"].id,
        reviewer_id=ctx["p3_pm"].id, status="pending_review", priority="high",
        due_date=_agodate(days=-3),
        created_at=_ago(days=16),
    )
    c26_09 = CapaRecord(
        capa_number=_cnum(2026),
        title="Drum Fill Station Overfill Event - DFB-002",
        severity="minor", source_type="self_initiated",
        source_description="Drum overfill by 3.2 kg detected during filling operation.",
        plant_id=ctx["p3"].id, affected_machine_id=machines["DFB-002"].id,
        affected_sku_id=skus["IPA-99"].id,
        deviation_description="Drum filling station DFB-002 overfilled a 200L IPA drum by 3.2 kg "
            "due to automatic cutoff valve failing to actuate at setpoint weight.",
        immediate_action="Cutoff valve replaced. Drum transferred to rework. No spillage occurred.",
        owner_id=ctx["p3_qa"].id, raised_by_id=ctx["p3_op1"].id,
        reviewer_id=None, status="open", priority="medium",
        due_date=_agodate(days=-8),
        created_at=_ago(days=6),
    )
    c26_10 = CapaRecord(
        capa_number=_cnum(2026),
        title="IPC Thickness Spec Deviation - Metformin 500mg",
        severity="minor", source_type="deviation",
        source_description="Tablet thickness out-of-spec during in-process check Shift B.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["TCA-001"].id,
        affected_sku_id=skus["MET-500T"].id,
        deviation_description="Tablet thickness measured at 4.85mm against specification 5.0-5.3mm "
            "on 6 samples during Shift B IPC check. Batch quarantined.",
        immediate_action="Compression gap adjusted. Resampling in progress.",
        owner_id=ctx["p1_ie1"].id, raised_by_id=ctx["p1_sup3"].id,
        reviewer_id=ctx["p1_qa"].id, status="open", priority="medium",
        due_date=_agodate(days=-20),
        created_at=_ago(days=3),
    )
    c26_11 = CapaRecord(
        capa_number=_cnum(2026),
        title="Packaging Line Downtime Spike - BPL-C",
        severity="minor", source_type="self_initiated",
        source_description="BPL-C showed three downtime events totalling 88 minutes in one shift.",
        plant_id=ctx["p1"].id, affected_machine_id=machines["BPC-001"].id,
        deviation_description="Blistering and Packaging Line C recorded three unplanned downtime events "
            "totalling 88 minutes in Shift A. Primary cause: blister film supply web break.",
        immediate_action="Film roll replaced. Tension settings adjusted.",
        owner_id=ctx["p1_ie2"].id, raised_by_id=ctx["p1_sup1"].id,
        reviewer_id=None, status="in_progress", priority="low",
        due_date=_agodate(days=-25),
        created_at=_ago(days=5),
    )
    c26_12 = CapaRecord(
        capa_number=_cnum(2026),
        title="Enrober Pump Seal Leak - CCL-001",
        severity="minor", source_type="deviation",
        source_description="Minor chocolate seal leak detected during Shift C inspection.",
        plant_id=ctx["p2"].id, affected_machine_id=machines["CCL-001"].id,
        deviation_description="Operator reported minor pump seal leakage on CCL-001 during Shift C. "
            "Risk of cross-contamination if not addressed.",
        immediate_action="Temporary compound applied. Machine scheduled for maintenance.",
        owner_id=ctx["p2_qa"].id, raised_by_id=ctx["p2_op2"].id,
        reviewer_id=ctx["p2_pm"].id, status="open", priority="medium",
        due_date=_agodate(days=-18),
        created_at=_ago(days=2),
    )

    all_capas = [c25_01, c25_02, c25_03, c25_04, c25_05, c25_06, c25_07, c25_08,
                 c26_01, c26_02, c26_03, c26_04, c26_05, c26_06,
                 c26_07, c26_08, c26_09, c26_10, c26_11, c26_12]
    db.session.add_all(all_capas)
    db.session.flush()

    ae_p1.capa_id = c26_03.id
    ae_p2.capa_id = c26_06.id
    db.session.flush()

    def _cc(capa, uid, body, days_ago):
        return CapaComment(capa_id=capa.id, user_id=uid, body=body, created_at=_ago(days=days_ago))

    comments = [
        _cc(c25_06, ctx["p1_pm"].id,
            "Bearing failure pattern is concerning. IE team please analyse the maintenance logs "
            "and determine if we need a redesigned lubrication schedule.", 44),
        _cc(c25_06, ctx["p1_ie1"].id,
            "Analysis underway. Bearing manufacturer recommends reducing interval from 500hr to 350hr. "
            "Draft revised PM procedure is attached to this CAPA.", 40),
        _cc(c25_06, ctx["p1_pm"].id,
            "Approved in principle. Waiting on spare bearing stock delivery before implementing. "
            "Please update status once stock confirmed.", 35),
        _cc(c26_01, ctx["p1_qa"].id,
            "Weight samples sent to QC lab for full assay. Results expected by tomorrow. "
            "Batch remains in quarantine.", 29),
        _cc(c26_01, ctx["p1_sup1"].id,
            "Compression force setting reviewed. Punch tooling shows wear pattern on 3 lower punches. "
            "Replacement requested from stores.", 27),
        _cc(c26_01, ctx["p1_ie1"].id,
            "Recommended increasing IPC frequency during first hour of each shift as interim measure. "
            "Updated SOP draft under review.", 24),
        _cc(c26_02, ctx["p1_qa"].id,
            "Metal particle test results received - all negative. Batch released for further processing. "
            "Root cause investigation ongoing.", 20),
        _cc(c26_02, ctx["p1_pm"].id,
            "Good outcome on metal test. Please ensure impact guard installation is verified by "
            "maintenance before closing this CAPA.", 18),
        _cc(c26_05, ctx["p2_pm"].id,
            "Cream depositor calibration completed. 15-minute weight monitoring in place. "
            "Continue for 5 more working days before requesting closure review.", 16),
        _cc(c26_05, ctx["p2_qa"].id,
            "Weight monitoring data reviewed - last 3 days all within spec. Escalating for closure review.", 8),
        _cc(c26_08, ctx["p3_pm"].id,
            "NaOH pump calibration completed. Re-analysis of Batch IPA-26-0018 in progress. "
            "Expecting results by end of week.", 14),
        _cc(c26_08, ctx["p3_qa"].id,
            "Batch re-analysis complete - pH 7.0, within spec. Batch released. "
            "Awaiting closure review from plant manager.", 9),
        _cc(c26_10, ctx["p1_qa"].id,
            "Compression gap adjusted. Initial resampling shows thickness at 5.05mm - within spec. "
            "Continuing monitoring for 2 shifts before requesting formal closure.", 2),
        _cc(c26_12, ctx["p2_pm"].id,
            "Pump seal replacement parts ordered. Maintenance slot booked for tomorrow morning. "
            "Production to avoid CCL-001 overnight if possible.", 1),
    ]
    db.session.add_all(comments)
    db.session.commit()
    return all_capas


def _build_rca(ctx, capas):
    capa_map = {c.capa_number: c for c in capas}
    rca_defs = [
        ("CAPA-2025-0001", ctx["p1_ie1"].id,
         "Tablet batch B25001 had 4 out-of-specification weight samples during IPC check.",
         "Why did tablets vary in weight?","Insufficient die fill volume at several stations.",
         "Why was die fill insufficient?","Lower punch tip wear caused variable fill depth.",
         "Why were punches worn?","Punch set had exceeded safe service life without inspection.",
         "Why was inspection missed?","Punch inspection interval lapsed by 1.5 weeks.",
         "Why did the interval lapse?","No automated reminder system existed; reliance on manual scheduling.",
         "Worn punch set in service beyond safe life due to manual PM scheduling with no automated reminders.",
         "machine"),
        ("CAPA-2025-0002", ctx["p1_ie1"].id,
         "Capsule fill weight QC samples showed 8 out-of-spec results in 2025 with no investigation.",
         "Why were fill weights out-of-spec?","Dosing disc was overfilling cavities intermittently.",
         "Why was the disc overfilling?","Dosing disc worn beyond tolerance - cavity depth increased.",
         "Why was disc wear not detected?","No scheduled replacement or dimensional inspection for dosing discs.",
         "Why was there no schedule?","Dosing disc was not included in the equipment PM master plan.",
         "Why was it omitted from PM?","PM plan was not updated after dosing disc was identified as critical.",
         "Dosing disc absent from PM master plan due to incomplete equipment criticality review at installation.",
         "method"),
        ("CAPA-2025-0005", ctx["p3_qa"].id,
         "Batch IPA-25-0072 released with purity 98.1%, below minimum specification of 99.0%.",
         "Why was purity below specification?","Raw material from supplier had actual purity 98.1%.",
         "Why was supplier CoA inaccurate?","Supplier used different analytical method producing inflated results.",
         "Why was CoA accepted without verification?","Incoming QC procedure did not require purity testing for this material.",
         "Why was the procedure insufficient?","Procedure was written when only visual inspection was considered adequate.",
         "Why was procedure not reviewed?","Supplier qualification review had not been performed for 3 years.",
         "Absence of incoming QC purity testing due to outdated supplier qualification and incoming QC procedure.",
         "material"),
        ("CAPA-2026-0003", ctx["p1_ie1"].id,
         "Rejection rate on Tablet Compression Line A reached 3.8% during Shift C - alert triggered.",
         "Why were so many tablets rejected?","High proportion of hardness and weight OOS failures at press stations 6, 8, 11.",
         "Why did those stations produce OOS tablets?","Punch tooling at those stations was worn past dimensional tolerance.",
         "Why were worn punches in service?","Punch inspection schedule had lapsed by 1.5 weeks.",
         "Why did the schedule lapse?","Punch change interval reminder was removed from scheduling system after software upgrade.",
         "Why was it not re-added?","No validation check was performed on PM schedules after the system migration.",
         "Worn punch tooling caused elevated rejection due to PM schedule loss during software migration without validation.",
         "machine"),
        ("CAPA-2026-0006", ctx["p2_ie"].id,
         "CCL-2 rejection rate 3.1% triggered alert. Primary defect: colour deviation on enrobed wafers.",
         "Why did wafers have colour deviation?","Chocolate coating appeared matt and uneven rather than glossy.",
         "Why was the coating uneven?","Chocolate tempering temperature running 0.8 degrees C below optimal range.",
         "Why was the tempering temperature low?","Ambient temperature in production hall was 2 degrees C above summer baseline.",
         "Why did ambient temperature affect setpoint?","No seasonal compensation was built into the tempering setpoint SOP.",
         "Why was there no seasonal compensation?","SOP was written during winter commissioning without considering seasonal variation.",
         "Inadequate tempering SOP with no seasonal compensation caused colour rejection under summer ambient conditions.",
         "environment"),
        ("CAPA-2026-0008", ctx["p3_qa"].id,
         "Batch IPA-26-0018 pH fell to 6.2 during neutralisation, below specification minimum of 6.8.",
         "Why did pH fall below specification?","NaOH dosing was insufficient to achieve full neutralisation.",
         "Why was NaOH dosing insufficient?","Dosing pump was delivering less than calibrated volume.",
         "Why was pump under-delivering?","Pump diaphragm had developed a partial failure reducing stroke volume.",
         "Why was diaphragm failure not detected?","Pump calibration check had not been performed for 9 weeks, exceeding 4-week interval.",
         "Why was calibration interval exceeded?","Resource shortage during planned maintenance period caused PM deferrals.",
         "Pump diaphragm failure went undetected due to PM deferral during resource shortage, causing pH excursion.",
         "machine"),
    ]
    for (cnum, analyst_id, prob,
         w1, a1, w2, a2, w3, a3, w4, a4, w5, a5,
         root, cat) in rca_defs:
        c = capa_map.get(cnum)
        if not c:
            continue
        db.session.add(RcaRecord(
            capa_id=c.id, analyst_id=analyst_id,
            problem_statement=prob,
            why_1=f"{w1} {a1}", why_2=f"{w2} {a2}", why_3=f"{w3} {a3}",
            why_4=f"{w4} {a4}", why_5=f"{w5} {a5}",
            root_cause_statement=root, root_cause_category=cat,
            similar_events_referenced=None, ai_suggestions_used=False,
            created_at=c.created_at + timedelta(days=3),
        ))
    db.session.commit()


def _build_improvements(ctx, perf):
    p1, p2, p3 = ctx["p1"], ctx["p2"], ctx["p3"]
    l_tcla, l_bpl1, l_ccl2 = ctx["l_tcla"], ctx["l_bpl1"], ctx["l_ccl2"]
    machines = ctx["machines"]

    def _opp(plant_id, title, desc, cat, line_id=None, machine_id=None,
              impact_min=None, evidence=None, data=None, score=0.0,
              status="new", accepted_by=None, dismissed_reason=None,
              deferred_until=None, gen_days_ago=10):
        db.session.add(ImprovementOpportunity(
            plant_id=plant_id, line_id=line_id, machine_id=machine_id,
            opportunity_title=title, opportunity_description=desc,
            category=cat, impact_minutes_per_shift=impact_min,
            impact_units_per_shift=None,
            evidence_summary=evidence, supporting_data=data,
            rank_score=score, status=status,
            accepted_by=accepted_by, dismissed_reason=dismissed_reason,
            deferred_until=deferred_until,
            generated_at=_ago(days=gen_days_ago),
            created_at=_ago(days=gen_days_ago),
        ))

    co_tcla = perf["changeover_per_line"].get(l_tcla.id, [])
    if co_tcla:
        avg = sum(co_tcla) / len(co_tcla)
        _opp(p1.id, f"{l_tcla.line_name} Changeover Above Standard",
             f"Average changeover on {l_tcla.line_name} is {avg:.0f} min across "
             f"{len(co_tcla)} events in the last 30 days (target: 40 min). "
             f"Implementing SMED principles and pre-staged change parts could reduce this to under 30 min.",
             "changeover_reduction", line_id=l_tcla.id,
             impact_min=round(avg - 40, 1),
             evidence=f"{len(co_tcla)} changeovers, avg {avg:.0f} min",
             data={"event_count": len(co_tcla), "avg_duration_min": round(avg, 1),
                   "target_min": 40, "excess_min": round(avg - 40, 1)},
             score=round(avg - 40, 1), status="accepted",
             accepted_by=ctx["p1_pm"].id, gen_days_ago=12)

    co_bpl1 = perf["changeover_per_line"].get(l_bpl1.id, [])
    if co_bpl1:
        avg = sum(co_bpl1) / len(co_bpl1)
        _opp(p2.id, f"{l_bpl1.line_name} Changeover Above Standard",
             f"Average changeover on {l_bpl1.line_name} is {avg:.0f} min across "
             f"{len(co_bpl1)} events in the last 30 days (target: 40 min). "
             f"Pre-staging trolleys and a dedicated changeover crew could reduce this to 35 min.",
             "changeover_reduction", line_id=l_bpl1.id,
             impact_min=round(avg - 40, 1),
             evidence=f"{len(co_bpl1)} changeovers, avg {avg:.0f} min",
             data={"event_count": len(co_bpl1), "avg_duration_min": round(avg, 1),
                   "target_min": 40, "excess_min": round(avg - 40, 1)},
             score=round(avg - 40, 1), status="deferred",
             deferred_until=_agodate(days=-30), gen_days_ago=10)

    ccl2_rej = perf["rejection_per_line"].get(l_ccl2.id, {})
    if ccl2_rej.get("units", 0) > 0:
        rate = ccl2_rej["rejected"] / ccl2_rej["units"] * 100
        if rate > 2.0:
            _opp(p2.id, f"Rising Rejection Rate on {l_ccl2.line_name}",
                 f"Rejection rate on {l_ccl2.line_name} is {rate:.2f}% over the last 14 days "
                 f"(target: 2%). Primary defect is colour deviation on enrobed product. "
                 f"Seasonal tempering compensation SOP should be prioritised.",
                 "rejection_reduction", line_id=l_ccl2.id,
                 evidence=f"{ccl2_rej['rejected']} rejects / {ccl2_rej['units']} units = {rate:.2f}%",
                 data={"total_units": ccl2_rej["units"], "total_rejected": ccl2_rej["rejected"],
                       "rate_pct": round(rate, 2), "target_pct": 2.0},
                 score=round(rate, 1), status="new", gen_days_ago=5)

    pareto = perf["pareto_all"]
    if pareto:
        total_all = sum(pareto.values())
        top_rc_id = max(pareto, key=pareto.get)
        top_min   = pareto[top_rc_id]
        top_rc    = ReasonCode.query.get(top_rc_id)
        if top_rc and total_all > 0:
            pct = top_min / total_all * 100
            for plant, pstatus, paccepted in [
                (p1, "accepted", ctx["p1_pm"].id),
                (p2, "new",      None),
                (p3, "new",      None),
            ]:
                _opp(plant.id, f"{top_rc.label} is top unplanned downtime cause",
                     f"{top_rc.label} accounts for {pct:.0f}% ({top_min:.0f} min) of all "
                     f"unplanned downtime in the last 30 days. Focused bearing maintenance and "
                     f"predictive monitoring can recover significant production time.",
                     "downtime_reduction",
                     impact_min=round(top_min / 30, 1),
                     evidence=f"{top_min:.0f} min ({pct:.0f}% of {total_all:.0f} min total unplanned)",
                     data={"rc_code": top_rc.code, "rc_label": top_rc.label,
                           "minutes": round(top_min, 0), "share_pct": round(pct, 1)},
                     score=round(pct, 1), status=pstatus, accepted_by=paccepted, gen_days_ago=7)

    cutoff_date = TODAY - timedelta(days=90)
    gap_targets = [
        ("CFB-003", machines["CFB-003"], p1, "new", None),
        ("CCL-002", machines["CCL-002"], p2, "new", None),
        ("DFB-001", machines["DFB-001"], p3, "dismissed", "Machine decommissioned for planned upgrade in Q3 2026."),
        ("CBA-001", machines["CBA-001"], p3, "new", None),
    ]
    for code, mach, plant, gstatus, gdismissed in gap_targets:
        latest = (MostStudy.query.filter_by(workstation_id=mach.id, status="published")
                  .order_by(MostStudy.study_date.desc()).first())
        if not latest or latest.study_date < cutoff_date:
            evid = ("No published MOST study on record" if not latest else
                    f"Last published: {latest.study_date} ({(TODAY - latest.study_date).days} days ago)")
            _opp(plant.id, f"Standard time outdated for {mach.machine_name}",
                 f"{mach.machine_name} has no published MOST study within the last 90 days. "
                 f"Update the standard time to keep performance metrics and OEE calculations accurate.",
                 "standard_time_update", machine_id=mach.id,
                 evidence=evid,
                 data={"machine_code": code,
                       "last_study_date": str(latest.study_date) if latest else None},
                 score=5.0, status=gstatus, dismissed_reason=gdismissed, gen_days_ago=3)

    db.session.commit()


def _build_preferences_and_leads(ctx):
    active = [u for u in ctx["all_users"]
              if u.is_active and not u.is_deleted and u.password_hash]
    prefs = []
    for u in active:
        prefs.append(UserPreference(
            user_id=u.id, view_name="dashboard_filters",
            config={"time_range": "last_7_days", "show_oee": True, "show_alerts": True},
            created_at=_ago(days=_rng.randint(10, 50)),
        ))
        if _rng.random() < 0.5:
            prefs.append(UserPreference(
                user_id=u.id, view_name="production_table_sort",
                config={"sort_col": "start_time", "sort_dir": "desc", "per_page": 20},
                created_at=_ago(days=_rng.randint(5, 30)),
            ))
    db.session.add_all(prefs)

    leads = [
        Lead(name="Karan Mehta",          email="karan.mehta@vikrampharmaceuticals.com",
             company="Vikram Pharmaceuticals Ltd",  role="Operations Director",
             facility_type="pharmaceutical",        phone="+91-98234-56789",
             message="Interested in the MOST module and OEE dashboard. Can we schedule a demo?",
             source="demo_request", created_at=_ago(days=25)),
        Lead(name="Preethi Raghunathan", email="preethi.r@sfbeverage.in",
             company="Sunrise Food and Beverages",  role="Plant Manager",
             facility_type="FMCG",                  phone="+91-97700-43210",
             message="Looking to reduce changeover times on packaging lines. Please send pricing information.",
             source="demo_request", created_at=_ago(days=18)),
        Lead(name="Ajit Kulkarni",        email="ajitkulkarni@infrachemicals.net",
             company="Infra Chemicals Pvt Ltd",      role="Quality Head",
             facility_type="process manufacturing",  phone="+91-96600-12345",
             message="Need a CAPA management tool integrated with production data. Platform looks promising.",
             source="contact", created_at=_ago(days=14)),
        Lead(name="Sangeeta Borkar",      email="sangeeta.borkar@alphaagrochem.com",
             company="Alpha Agrochem Industries",    role="IE Manager",
             facility_type="process manufacturing",
             message="Request demo for MOST work study and standard time setting module.",
             source="demo_request", created_at=_ago(days=10)),
        Lead(name="Deepak Nath",          email="deepak.nath@globesnacks.co.in",
             company="Globe Snacks Pvt Ltd",          role="Manufacturing Head",
             facility_type="FMCG",                  phone="+91-98800-55667",
             message="Looking for OEE tracking solution for 3 plants. Please contact.",
             source="demo_request", created_at=_ago(days=7)),
        Lead(name="Rashmi Bhatt",         email="rashmi.bhatt@precisionpharma.in",
             company="Precision Pharma Solutions",   role="Validation Manager",
             facility_type="pharmaceutical",
             message="Interested in CAPA and RCA module. Need GMP-compliant audit trail.",
             source="contact", created_at=_ago(days=4)),
        Lead(name="Vikram Desai",         email="vikram.desai@greenchemicals.co",
             company="Green Chemicals Co.",           role="Plant Manager",
             facility_type="process manufacturing",
             message="Can IntelliMOST integrate with our existing ERP? Need integration details.",
             source="demo_request", created_at=_ago(days=1)),
    ]
    db.session.add_all(leads)
    db.session.commit()


def _build_audit_logs(ctx, capas):
    sa, adm = ctx["sa"], ctx["adm"]
    capa_map = {c.capa_number: c for c in capas}
    logs = []

    for u in ctx["all_users"]:
        if u.password_hash:
            logs.append(_audit(
                sa.id if u.role == "admin" else u.id,
                "USER_REGISTERED", "User", u.id,
                f"User {u.email} registered with role {u.role}",
                when=u.created_at + timedelta(minutes=5),
            ))

    for p in ctx["plants"]:
        logs.append(_audit(sa.id, "PLANT_CREATED", "Plant", p.id,
                           f"Plant '{p.name}' created ({p.industry_type})",
                           when=p.created_at + timedelta(minutes=2)))

    for ln in ctx["all_lines"]:
        mgr = ctx["pm"][ln.plant_id]
        logs.append(_audit(mgr.id, "LINE_CREATED", "ProductionLine", ln.id,
                           f"Line '{ln.line_name}' created",
                           when=ln.created_at + timedelta(minutes=3)))

    for code, mach in ctx["machines"].items():
        line = ProductionLine.query.get(mach.line_id)
        if line:
            mgr = ctx["pm"][line.plant_id]
            logs.append(_audit(mgr.id, "MACHINE_CREATED", "Machine", mach.id,
                               f"Machine {code} added to {line.line_name}",
                               when=mach.created_at + timedelta(minutes=5)))

    for u in ctx["all_users"]:
        if u.is_active and not u.is_deleted and u.last_login and u.last_login >= _ago(hours=24):
            logs.append(_audit(u.id, "USER_LOGIN", "User", u.id,
                               f"{u.email} signed in",
                               when=u.last_login, ua=UA_DESK))

    recent_outputs = (ProductionOutput.query
                      .filter(ProductionOutput.logged_at >= _ago(hours=24))
                      .limit(30).all())
    for out in recent_outputs:
        logs.append(_audit(out.logged_by, "OUTPUT_LOGGED", "Shift", out.shift_id,
                           f"+{out.quantity} units logged (cumulative {out.cumulative_total})",
                           when=out.logged_at))

    recent_dt = (DowntimeEvent.query
                 .filter(DowntimeEvent.created_at >= _ago(days=5),
                         DowntimeEvent.event_type == "unplanned")
                 .limit(20).all())
    for dt in recent_dt:
        logs.append(_audit(dt.logged_by, "DOWNTIME_LOGGED", "DowntimeEvent", dt.id,
                           f"Unplanned downtime started on machine {dt.machine_id}",
                           when=dt.created_at))
        if dt.is_resolved and dt.end_time:
            logs.append(_audit(dt.logged_by, "DOWNTIME_CLOSED", "DowntimeEvent", dt.id,
                               f"Downtime resolved: {dt.duration_minutes:.0f} min",
                               when=dt.end_time + timedelta(minutes=1)))

    recent_rej = (RejectionEvent.query
                  .filter(RejectionEvent.created_at >= _ago(days=3))
                  .limit(15).all())
    for rj in recent_rej:
        logs.append(_audit(rj.logged_by, "REJECTION_LOGGED", "RejectionEvent", rj.id,
                           f"{rj.quantity_rejected} units rejected: {rj.defect_type}",
                           when=rj.created_at))

    for s in MostStudy.query.all():
        aid = s.analyst_id
        logs.append(_audit(aid, "STUDY_SAVED_DRAFT", "MostStudy", s.id,
                           f"Study '{s.study_name}' saved as draft",
                           when=s.created_at + timedelta(hours=1)))
        if s.status == "published" and s.published_at:
            logs.append(_audit(aid, "STUDY_PUBLISHED", "MostStudy", s.id,
                               f"Study '{s.study_name}' published (v{s.version})",
                               when=s.published_at))
        if s.status == "archived":
            logs.append(_audit(aid, "STUDY_ARCHIVED", "MostStudy", s.id,
                               f"Study '{s.study_name}' archived",
                               when=s.created_at + timedelta(days=2)))
        if s.status == "under_revision":
            logs.append(_audit(aid, "STUDY_REVISED", "MostStudy", s.id,
                               f"Study '{s.study_name}' placed under revision",
                               when=s.created_at + timedelta(hours=2)))

    for c in capas:
        logs.append(_audit(c.raised_by_id, "CAPA_CREATED", "CapaRecord", c.id,
                           f"{c.capa_number} created: {c.title[:60]}",
                           when=c.created_at + timedelta(minutes=5)))
        if c.status in ("in_progress", "pending_review", "closed", "overdue"):
            logs.append(_audit(c.owner_id, "CAPA_STATUS_CHANGED", "CapaRecord", c.id,
                               f"{c.capa_number} status updated to {c.status}",
                               when=c.created_at + timedelta(days=2)))
        if c.status == "closed" and c.closed_at:
            logs.append(_audit(c.owner_id, "CAPA_STATUS_CHANGED", "CapaRecord", c.id,
                               f"{c.capa_number} closed",
                               when=c.closed_at))

    for ae in AlertEvent.query.filter(AlertEvent.status == "acknowledged").all():
        if ae.acknowledged_by and ae.acknowledged_at:
            logs.append(_audit(ae.acknowledged_by, "ALERT_ACKNOWLEDGED",
                               "AlertEvent", ae.id,
                               f"Alert #{ae.id} acknowledged: action={ae.action_taken}",
                               when=ae.acknowledged_at))

    for opp in ImprovementOpportunity.query.all():
        if opp.status == "accepted" and opp.accepted_by:
            logs.append(_audit(opp.accepted_by, "IMPROVEMENT_ACCEPTED",
                               "ImprovementOpportunity", opp.id,
                               f"Opportunity accepted: {opp.opportunity_title[:60]}",
                               when=opp.generated_at + timedelta(days=1)))
        elif opp.status == "dismissed":
            pm_id = ctx["pm"][opp.plant_id].id
            logs.append(_audit(pm_id, "IMPROVEMENT_DISMISSED",
                               "ImprovementOpportunity", opp.id,
                               f"Opportunity dismissed: {opp.opportunity_title[:60]}",
                               when=opp.generated_at + timedelta(days=1)))
        elif opp.status == "deferred":
            pm_id = ctx["pm"][opp.plant_id].id
            logs.append(_audit(pm_id, "IMPROVEMENT_DEFERRED",
                               "ImprovementOpportunity", opp.id,
                               f"Opportunity deferred: {opp.opportunity_title[:60]}",
                               when=opp.generated_at + timedelta(days=1)))

    for u in [ctx["p1_ie1"], ctx["p2_ie"], ctx["p3_ie"]]:
        logs.append(_audit(u.id, "PROFILE_UPDATED", "User", u.id,
                           f"{u.email} updated profile - certification level updated",
                           when=_ago(days=_rng.randint(20, 50))))

    p1_op2 = ctx["p1_op2"]
    logs.append(_audit(ctx["p1_pm"].id, "USER_UPDATED", "User", p1_op2.id,
                       f"{p1_op2.email} account locked after 5 failed login attempts",
                       when=p1_op2.last_login + timedelta(minutes=2)))

    deactivated = next(u for u in ctx["all_users"] if u.email == "prakash.rao@nutricraftfoods.com")
    logs.append(_audit(ctx["p2_pm"].id, "USER_DEACTIVATED", "User", deactivated.id,
                       "User account deactivated - employment ended",
                       when=_ago(days=45)))

    invited = ctx["p1_op4"]
    logs.append(_audit(ctx["p1_pm"].id, "USER_INVITED", "User", invited.id,
                       f"Invitation email sent to {invited.email}",
                       when=_ago(days=1)))

    logs.append(_audit(sa.id, "ALERT_RULE_CREATED", "AlertRule", None,
                       "Alert rules initialised for all three plants",
                       when=_ago(days=55)))

    for rca in RcaRecord.query.all():
        logs.append(_audit(rca.analyst_id, "RCA_COMPLETED", "RcaRecord", rca.id,
                           f"RCA completed for CAPA #{rca.capa_id}: category={rca.root_cause_category}",
                           when=rca.created_at + timedelta(hours=2)))

    db.session.add_all(logs)
    db.session.commit()


def _print_summary(ctx):
    counts = {
        "Plants":              Plant.query.count(),
        "Users":               User.query.count(),
        "Production Lines":    ProductionLine.query.count(),
        "Machines":            Machine.query.count(),
        "SKUs":                SKU.query.count(),
        "Reason Codes":        ReasonCode.query.count(),
        "Shifts":              Shift.query.count(),
        "Production Outputs":  ProductionOutput.query.count(),
        "Downtime Events":     DowntimeEvent.query.count(),
        "Rejection Events":    RejectionEvent.query.count(),
        "MOST Studies":        MostStudy.query.count(),
        "MOST Elements":       MostElement.query.count(),
        "CAPA Records":        CapaRecord.query.count(),
        "CAPA Comments":       CapaComment.query.count(),
        "RCA Records":         RcaRecord.query.count(),
        "Alert Rules":         AlertRule.query.count(),
        "Alert Events":        AlertEvent.query.count(),
        "Improvement Opps":    ImprovementOpportunity.query.count(),
        "Audit Logs":          AuditLog.query.count(),
        "User Preferences":    UserPreference.query.count(),
        "Leads":               Lead.query.count(),
    }
    print("\n" + "=" * 62)
    print("  IntelliMOST Seed Complete")
    print("=" * 62)
    print("\nRecords Created:")
    for entity, n in counts.items():
        print(f"  {entity:<28} {n:>6}")
    print("\n\nDemo Login Credentials")
    print("-" * 62)
    for role, pw in SEED_PASSWORDS.items():
        print(f"  {role:<20} {pw}")
    print()
    print(f"  super_admin            {ctx['sa'].email}")
    print(f"  admin                  {ctx['adm'].email}")
    print()
    print("  [Plant 1 - Pharma Excellence Ltd (enterprise)]")
    print(f"    plant_manager          {ctx['p1_pm'].email}")
    print(f"    industrial_engineer    {ctx['p1_ie1'].email}")
    print(f"    qa_manager             {ctx['p1_qa'].email}")
    print(f"    shift_supervisor       {ctx['p1_sup1'].email}")
    print(f"    operator               {ctx['p1_op1'].email}")
    print()
    print("  [Plant 2 - NutriCraft Foods Pvt Ltd (professional)]")
    print(f"    plant_manager          {ctx['p2_pm'].email}")
    print(f"    industrial_engineer    {ctx['p2_ie'].email}")
    print(f"    qa_manager             {ctx['p2_qa'].email}")
    print(f"    shift_supervisor       {ctx['p2_sup1'].email}")
    print()
    print("  [Plant 3 - ChemFlow Process Industries (starter)]")
    print(f"    plant_manager          {ctx['p3_pm'].email}")
    print(f"    industrial_engineer    {ctx['p3_ie'].email}")
    print(f"    qa_manager             {ctx['p3_qa'].email}")
    print(f"    shift_supervisor       {ctx['p3_sup'].email}")
    print()
    print("  Special user states:")
    print("    locked account         deepa.verma@pharmaexcellence.in (5 failed attempts)")
    print("    pending invitation     pooja.sharma@pharmaexcellence.in (no password yet)")
    print("    deactivated            prakash.rao@nutricraftfoods.com (is_deleted=True)")
    print("=" * 62 + "\n")


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        run_seed()
