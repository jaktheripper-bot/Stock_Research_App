import os
import logging

# Suppress Streamlit bare-mode log spam
os.environ["STREAMLIT_LOG_LEVEL"] = "error"
logging.getLogger("streamlit").setLevel(logging.ERROR)

from streamlit.testing.v1 import AppTest

def test_app_loads_and_has_search_box():
    print("Testing Streamlit app headless initialization...")
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    
    # Assert app loads without unhandled exceptions
    assert not at.exception, f"App crashed on launch: {at.exception}"
    print("✅ App loads cleanly without unhandled exceptions.")
    
    # Assert query input exists
    inputs = [w for w in at.text_input]
    assert len(inputs) > 0, "No text input found for stock query."
    print(f"✅ Verified stock query input widget (found {len(inputs)} text input[s]).")

if __name__ == "__main__":
    test_app_loads_and_has_search_box()
    print("🎉 Headless UI smoke test passed.")
