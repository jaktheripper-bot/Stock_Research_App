from streamlit.testing.v1 import AppTest

def test_app_loads_without_errors():
    at = AppTest.from_file("app.py")
    at.run()
    assert not at.exception
    assert len(at.title) == 1
    assert "Automated Equity Research Terminal" in at.title[0].value
