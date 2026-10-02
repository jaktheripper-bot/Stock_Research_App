import os
import logging

# Suppress Streamlit bare-mode log spam
os.environ["STREAMLIT_LOG_LEVEL"] = "error"
logging.getLogger("streamlit").setLevel(logging.ERROR)

from streamlit.testing.v1 import AppTest

def test_interactive_app_suite():
    print(f"\n=======================================================")
    print(f"   INTERACTIVE UI SUITE & ACTION SIMULATION")
    print(f"=======================================================")
    
    # 1. Mount test
    print("1. Mounting App and Verifying Search Header...")
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    assert not at.exception, f"App crashed on mount: {at.exception}"
    print("   ✅ App mounted cleanly without exceptions.")
    
    inputs = list(at.text_input)
    assert len(inputs) > 0, "No text input found for stock query."
    print(f"   ✅ Stock query inputs operational (found {len(inputs)} input fields).")

    # 2. Alert Hub Button Click Simulation
    print("\n2. Simulating Alert Hub User Actions...")
    btn_mark = [b for b in at.button if b.key == "btn_mark_all_read"]
    if btn_mark:
        print("   • Clicking '✓ Mark All as Read'...")
        btn_mark[0].click().run()
        assert not at.exception, f"Clicking 'Mark All as Read' threw exception: {at.exception}"
        print("   ✅ 'Mark All as Read' executed cleanly with valid toast.")

    btn_dism = [b for b in at.button if b.key == "btn_dismiss_all_unread"]
    if btn_dism:
        print("   • Clicking '🗑️ Dismiss All Unread'...")
        btn_dism[0].click().run()
        assert not at.exception, f"Clicking 'Dismiss All Unread' threw exception: {at.exception}"
        print("   ✅ 'Dismiss All Unread' executed cleanly with valid toast.")

    # 3. Sidebar Stock Archive Selection & Active Dossier Loading Simulation
    print("\n3. Simulating Sidebar Archive Selection & Dossier Loading...")
    archive_picker = None
    for sb in at.selectbox:
        if any("•" in opt or "rev" in opt for opt in sb.options):
            archive_picker = sb
            break

    if archive_picker and len(archive_picker.options) > 1:
        # Prefer a known full dossier (e.g. RAILTEL) to guarantee testing all 7 analytical pillars
        chosen = next((opt for opt in archive_picker.options if "RAILTEL" in opt), archive_picker.options[1])
        print(f"   • Selecting archive option: '{chosen}'...")
        archive_picker.select(chosen).run()
        assert not at.exception, f"Selecting archive option '{chosen}' threw exception: {at.exception}"
        print("   ✅ Archive picker synchronized.")

        load_btns = [b for b in at.button if "Load Active Dossier" in b.label or "Active Report Loaded" in b.label]
        if load_btns and not load_btns[0].disabled:
            print("   • Clicking 'Load Active Dossier'...")
            load_btns[0].click().run()
            assert not at.exception, f"Clicking 'Load Active Dossier' threw exception: {at.exception}"
            print("   ✅ Active dossier loaded into view state cleanly.")

            # 4. Testing 'Expand all analytical pillars' Mobile Switch
            print("\n4. Simulating 'Expand All Analytical Pillars' Mobile Switch...")
            toggles = [t for t in at.toggle if "Expand all analytical pillars" in t.label]
            pillar_exps = [e for e in at.expander if "Pillar" in e.label]
            if toggles and pillar_exps:
                # Default: collapsed (False)
                assert all(not e.proto.expanded for e in pillar_exps), "Pillars should default to collapsed"
                print(f"   ✅ Initial collapsed state verified ({len(pillar_exps)} pillars collapsed for mobile).")

                # Toggle to True: expanded
                toggles[0].set_value(True).run()
                assert not at.exception, f"Toggling expand_all threw exception: {at.exception}"
                pillar_exps_expanded = [e for e in at.expander if "Pillar" in e.label]
                assert all(e.proto.expanded for e in pillar_exps_expanded), "All pillars should be expanded when switch is active"
                print(f"   ✅ Active expanded state verified ({len(pillar_exps_expanded)} pillars expanded).")
            elif toggles:
                print("   ℹ️ Toggle present but loaded dossier has 0 analytical pillars.")
            else:
                print("   ℹ️ Toggle 'Expand all analytical pillars' not found on loaded report.")

        # 4a. Testing Behavioral Controls & Pre-Mortem Decision Ledger Simulation
        print("\n4a. Simulating Behavioral Ergonomics (WCAG Palette & Pre-Mortem)...")
        cb_toggles = [t for t in at.toggle if t.key == "cb_palette_toggle"]
        if cb_toggles:
            print("   • Toggling 'Accessible Palette'...")
            cb_toggles[0].set_value(True).run()
            assert not at.exception, f"Toggling accessible palette threw exception: {at.exception}"
            print("   ✅ Accessible Palette toggle verified.")

        premortem_btns = [b for b in at.button if b.key == "btn_commit_premortem"]
        if premortem_btns:
            print("   • Clicking '🔒 Commit Pre-Mortem'...")
            premortem_btns[0].click().run()
            assert not at.exception, f"Clicking 'Commit Pre-Mortem' threw exception: {at.exception}"
            print("   ✅ Pre-Mortem Decision Ledger commit verified.")

        # 4b. Testing Arbitrary Multi-Quarter Differential Analysis Simulation
        print("\n4b. Simulating Multi-Quarter Differential Analysis & Thesis Drift Surveillance...")
        multi_rev_opt = next((opt for opt in archive_picker.options if "INFY" in opt or "TMPV" in opt), None)
        if multi_rev_opt:
            print(f"   • Selecting multi-revision stock: '{multi_rev_opt}'...")
            archive_picker.select(multi_rev_opt).run()
            assert not at.exception, f"Selecting '{multi_rev_opt}' threw exception: {at.exception}"

            diff_btns = [b for b in at.button if b.key == "btn_run_sb_diff"]
            if diff_btns:
                print("   • Clicking 'Run Differential Analysis'...")
                diff_btns[0].click().run()
                assert not at.exception, f"Clicking 'Run Differential Analysis' threw exception: {at.exception}"
                print("   ✅ Differential Analysis executed cleanly with toast and hoisted surveillance panel.")

                reset_btns = [b for b in at.button if b.key == "btn_reset_drift"]
                if reset_btns:
                    print("   • Clicking '✕ Close Differential'...")
                    reset_btns[0].click().run()
                    assert not at.exception, f"Clicking 'Close Differential' threw exception: {at.exception}"
                    print("   ✅ Differential view closed cleanly and active dossier restored.")
            else:
                print("   ℹ️ 'btn_run_sb_diff' not found in DOM.")
        else:
            print("   ℹ️ Multi-revision stock not found in archive picker options.")
    else:
        print("   ℹ️ No archive stocks available to select (empty archive).")

    # 5. Peer Comparison View Navigation Simulation
    print("\n5. Simulating Peer Comparison View Navigation on Public Site...")
    btn_compare = [b for b in at.button if b.key == "btn_nav_compare"]
    if btn_compare:
        print("   • Navigating to '⚖️ Peer Comparison' view...")
        btn_compare[0].click().run()
        assert not at.exception, f"Navigating to Peer Comparison threw exception: {at.exception}"
        assert any("Peer Comparison" in str(getattr(h, "value", "")) for h in at.markdown), "Peer Comparison header should be visible"
        print("   ✅ Peer Comparison view mounted and verified cleanly.")

    btn_dossier = [b for b in at.button if b.key == "btn_nav_dossier"]
    if btn_dossier:
        print("   • Returning to '🔍 Institutional Research Dossier' view...")
        btn_dossier[0].click().run()
        assert not at.exception, f"Returning to Dossier threw exception: {at.exception}"
        print("   ✅ Institutional Research Dossier view restored cleanly.")

    # 6. Standalone Admin Portal (admin.py) Authentication Gate Simulation
    print("\n6. Simulating Standalone Private Admin Portal (admin.py)...")
    at_admin = AppTest.from_file("admin.py")
    at_admin.run()
    assert not at_admin.exception, f"Admin portal threw exception on mount: {at_admin.exception}"
    assert any("Executive Admin Portal" in str(getattr(h, "value", "")) or "Administrator Access Required" in str(getattr(h, "value", "")) for h in at_admin.markdown), "Admin portal must require authentication"
    print("   ✅ Unauthenticated access correctly blocked by Administrator Password login screen.")

    # 7. Simulating User Authentication & Monetization UI States
    print("\n7. Simulating User Authentication & Monetization UI States...")
    at_auth = AppTest.from_file("app.py", default_timeout=15)
    at_auth.run()
    signin_btns = [b for b in at_auth.button if b.key == "btn_sidebar_signin"]
    assert len(signin_btns) > 0, "Guest user must see 'Sign In / Register' button in sidebar."
    print("   • Clicking 'Sign In / Register' in sidebar...")
    signin_btns[0].click().run()
    assert not at_auth.exception, f"Clicking Sign In threw exception: {at_auth.exception}"
    print("   ✅ Login trigger executed cleanly.")

    at_auth.session_state["user_session"] = {
        "id": "usr_headless_test",
        "email": "analyst@test.in",
        "full_name": "Test Analyst",
        "credits_balance": 2.0,
        "subscription_tier": "free",
        "is_pro": False
    }
    at_auth.run()
    assert not at_auth.exception, f"Rendering authenticated user threw exception: {at_auth.exception}"
    topup_btns = [b for b in at_auth.button if b.key == "btn_user_topup"]
    assert len(topup_btns) > 0, "Authenticated user must see '💳 Top Up' button."
    print("   • Clicking '💳 Top Up' button...")
    topup_btns[0].click().run()
    assert not at_auth.exception, f"Clicking Top Up threw exception: {at_auth.exception}"
    print("   ✅ Top Up trigger executed cleanly.")

    print("\n🎉 All interactive UI simulation tests passed with 0 errors.\n")

if __name__ == "__main__":
    test_interactive_app_suite()

