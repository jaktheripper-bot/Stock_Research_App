import os
from streamlit.testing.v1 import AppTest

def test_app_loads_without_errors():
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.title) == 1
    assert "Equity Research" in at.title[0].value

if __name__ == "__main__":
    test_app_loads_without_errors()
    print("🎉 tests/test_app.py passed successfully.")
