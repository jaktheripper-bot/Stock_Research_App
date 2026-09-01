{\rtf1\ansi\ansicpg1252\cocoartf2870
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import os\
import textwrap\
\
files = \{\
    "app.py": """\
        import streamlit as st\
        from analyzer import generate_stock_report\
\
        st.set_page_config(page_title="Stock Research Terminal", layout="wide")\
        st.title("Automated Equity Research Terminal")\
\
        api_key = st.secrets.get("GEMINI_API_KEY")\
        ticker_input = st.text_input("Enter Company Name or Ticker (e.g., Apple, Tata Motors, AAPL):", "").upper()\
\
        if st.button("Generate Research Report"):\
            if not api_key:\
                st.error("Gemini API key is missing.")\
            elif not ticker_input:\
                st.warning("Please enter a valid ticker.")\
            else:\
                with st.spinner(f"Analyzing \{ticker_input\}..."):\
                    try:\
                        report_text = generate_stock_report(ticker_input)\
                        st.markdown(report_text)\
                    except Exception as e:\
                        st.error(str(e))\
    """,\
    "normalizer.py": """\
        def format_indian_currency(val) -> str:\
            try:\
                num = float(val)\
            except (ValueError, TypeError):\
                return "N/A"\
\
            if num >= 10_000_000:\
                crores = num / 10_000_000\
                return f"\uc0\u8377 \{crores:,.2f\} Cr"\
            elif num >= 100_000:\
                lakhs = num / 100_000\
                return f"\uc0\u8377 \{lakhs:,.2f\} Lakh"\
            else:\
                return f"\uc0\u8377 \{num:,.2f\}"\
\
        def normalize_stock_data(raw_data: dict, exchange: str = "NSE") -> dict:\
            normalized = raw_data.copy()\
            raw_mcap = raw_data.get("market_cap")\
            \
            if exchange in ["NSE", "BSE", "NSEI", "BOM"]:\
                normalized["formatted_market_cap"] = format_indian_currency(raw_mcap)\
                normalized["currency"] = "INR"\
            else:\
                try:\
                    num = float(raw_mcap)\
                    normalized["formatted_market_cap"] = f"$\{num/1_000_000_000:,.2f\} B"\
                    normalized["currency"] = "USD"\
                except (ValueError, TypeError):\
                    normalized["formatted_market_cap"] = "N/A"\
                    normalized["currency"] = "Unknown"\
\
            return normalized\
    """,\
    "db.py": """\
        import streamlit as st\
        from supabase import create_client, Client\
\
        @st.cache_resource\
        def init_supabase() -> Client:\
            url = st.secrets["supa"]["url"]\
            key = st.secrets["supa"]["key"]\
            return create_client(url, key)\
\
        def fetch_archive():\
            supabase = init_supabase()\
            response = supabase.table("stock_archive").select("*").order("discovery_date", desc=True).execute()\
            return response.data\
\
        def save_report_to_archive(data: dict, report_text: str):\
            supabase = init_supabase()\
            payload = \{\
                "ticker": data.get("ticker"),\
                "short_name": data.get("short_name"),\
                "sector": data.get("sector"),\
                "industry": data.get("industry"),\
                "market_cap": str(data.get("market_cap")),\
                "pe_ratio": str(data.get("pe_ratio")),\
                "report_markdown": report_text\
            \}\
            supabase.table("stock_archive").upsert(payload, on_conflict="ticker").execute()\
    """,\
    "analyzer.py": """\
        import os\
        import requests\
        import streamlit as st\
        from google import genai\
        from normalizer import normalize_stock_data\
        from db import save_report_to_archive\
\
        @st.cache_data(ttl=3600)\
        def get_stock_fundamentals(query: str):\
            api_key = st.secrets.get("TWELVE_DATA_API_KEY", "demo")\
            \
            search_url = f"https://api.twelvedata.com/symbol_search?symbol=\{query\}&apikey=\{api_key\}"\
            response = requests.get(search_url)\
            response.raise_for_status()\
            result = response.json()\
            \
            if "code" in result and result["code"] != 200:\
                raise ValueError(f"Twelve Data API Error: \{result.get('message', 'Unknown error')\}")\
            \
            matches = result.get("data", [])\
            if not matches:\
                raise ValueError(f"Could not find a valid ticker for '\{query\}'.")\
                \
            ticker_symbol = matches[0]["symbol"]\
            exchange = matches[0].get("exchange", "NSE")\
            \
            for match in matches:\
                if match.get("exchange") in ["NSE", "BSE"]:\
                    ticker_symbol = match["symbol"]\
                    exchange = match["exchange"]\
                    break\
\
            profile_res = requests.get(f"https://api.twelvedata.com/profile?symbol=\{ticker_symbol\}&apikey=\{api_key\}").json()\
            stats_res = requests.get(f"https://api.twelvedata.com/statistics?symbol=\{ticker_symbol\}&apikey=\{api_key\}").json()\
            \
            valuations = stats_res.get("statistics", \{\}).get("valuations_metrics", \{\})\
            \
            raw_data = \{\
                "ticker": ticker_symbol,\
                "short_name": profile_res.get("name", ticker_symbol),\
                "sector": profile_res.get("sector", "N/A"),\
                "industry": profile_res.get("industry", "N/A"),\
                "market_cap": profile_res.get("market_capitalization", "N/A"),\
                "pe_ratio": valuations.get("trailing_pe", "N/A"),\
                "description": profile_res.get("description", "N/A")\
            \}\
            \
            return normalize_stock_data(raw_data, exchange=exchange)\
\
        REPORT_SYSTEM_PROMPT = \\"\\"\\"\
        You are an equity research analyst. Generate a comprehensive stock research report based on the provided metrics using strict Markdown. \
        All financial figures provided are in Indian Rupees (INR) unless explicitly stated otherwise. Express market values in Crores (Cr).\
        \\"\\"\\"\
\
        def generate_stock_report(ticker: str) -> str:\
            stock_data = get_stock_fundamentals(ticker)\
            api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")\
            client = genai.Client(api_key=api_key)\
            \
            user_prompt = f"Generate the research report for: \{stock_data.get('short_name')\} (\{stock_data.get('ticker')\})\\\\nData: \{stock_data\}"\
            \
            response = client.models.generate_content(\
                model="gemini-3.6-flash",\
                contents=user_prompt,\
                config=genai.types.GenerateContentConfig(\
                    system_instruction=REPORT_SYSTEM_PROMPT\
                ),\
            )\
            report_text = response.text\
            \
            try:\
                save_report_to_archive(stock_data, report_text)\
            except Exception as e:\
                print(f"Warning: Failed to save to archive: \{e\}")\
                \
            return report_text\
    """,\
    "requirements.txt": """\
        streamlit\
        supabase==2.12.0\
        pandas\
        google-genai\
        requests\
        pytest\
    """,\
    "tests/test_app.py": """\
        from streamlit.testing.v1 import AppTest\
\
        def test_app_loads_without_errors():\
            at = AppTest.from_file("app.py")\
            at.run()\
            assert not at.exception\
            assert len(at.title) == 1\
            assert "Automated Equity Research Terminal" in at.title[0].value\
    """\
\}\
\
os.makedirs("tests", exist_ok=True)\
for filepath, content in files.items():\
    cleaned_content = textwrap.dedent(content).strip()\
    with open(filepath.strip(), "w", encoding="utf-8") as f:\
        f.write(cleaned_content + "\\n")\
    print(f"Successfully generated: \{filepath.strip()\}")}