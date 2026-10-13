import unittest
from core.brand.moatnomics_house import MOATNOMICS_BRAND_HOUSE, get_system_prompt_context
from core.brand import MOATNOMICS_BRAND_HOUSE as EXPORTED_HOUSE, get_system_prompt_context as exported_context_fn

class TestMoatnomicsBrandHouse(unittest.TestCase):
    def test_brand_house_structure(self):
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["brand_name"], "Moatnomics")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["tagline"], "Audit the Asset. Protect the Allocator.")
        self.assertIn("Dual-Mandate", MOATNOMICS_BRAND_HOUSE["core_philosophy"])
        self.assertIn("Clinical, objective, empirical", MOATNOMICS_BRAND_HOUSE["tone_and_voice"])
        self.assertIn("NEVER output prescriptive advice", MOATNOMICS_BRAND_HOUSE["sebi_safe_harbor_rules"])
        self.assertIsInstance(MOATNOMICS_BRAND_HOUSE["forbidden_vocabulary"], list)
        self.assertIn("Multibagger", MOATNOMICS_BRAND_HOUSE["forbidden_vocabulary"])
        self.assertIn("AI Prediction", MOATNOMICS_BRAND_HOUSE["forbidden_vocabulary"])
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["taxonomy"]["Equities"], "Moatnomics Equities")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["taxonomy"]["Funds"], "Moatnomics Funds")
        self.assertEqual(MOATNOMICS_BRAND_HOUSE["taxonomy"]["Debt"], "Moatnomics Yield")

    def test_system_prompt_context_compilation(self):
        ctx = get_system_prompt_context()
        self.assertIsInstance(ctx, str)
        self.assertIn("You represent Moatnomics", ctx)
        self.assertIn("Dual-Mandate", ctx)
        self.assertIn("NEVER output prescriptive advice", ctx)

    def test_package_exports(self):
        self.assertIs(MOATNOMICS_BRAND_HOUSE, EXPORTED_HOUSE)
        self.assertIs(get_system_prompt_context, exported_context_fn)

if __name__ == "__main__":
    unittest.main()
