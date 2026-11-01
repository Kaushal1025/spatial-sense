"""Tests for the SAM 3.1 output parser. Run with: python3 -m unittest server/test_sam.py"""

import unittest

from sam import parse_output

# Real output_text from a SAM 3.1 response (mask payload truncated).
REAL_OUTPUT = (
    "<0f>0<|box;x1=273;y1=256;x2=395;y2=568;w=480;h=640;c=0.9726027250289917|>"
    "<|mask;x=0;y=0;c=0.9726027250289917;data=313,123,~!#CX#K{%%VPLVxREcGl...|>"
)


class ParseOutputTest(unittest.TestCase):
    def assertBboxAlmostEqual(self, actual, expected):
        self.assertEqual(len(actual), 4)
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=4)

    def test_real_output(self):
        regions = parse_output(REAL_OUTPUT, "person")
        self.assertEqual(len(regions), 1)
        region = regions[0]
        self.assertEqual(region["label"], "person")
        self.assertAlmostEqual(region["score"], 0.9726, places=4)
        self.assertBboxAlmostEqual(region["bbox"], [0.56875, 0.4, 0.8229167, 0.8875])
        # Mask data is ignored, not passed through.
        self.assertEqual(set(region), {"label", "score", "bbox"})

    def test_empty_output(self):
        self.assertEqual(parse_output("", "person"), [])

    def test_two_boxes(self):
        output = (
            "<0f>0<|box;x1=100;y1=200;x2=300;y2=400;w=1000;h=800;c=0.9|>"
            "<|mask;x=0;y=0;c=0.9;data=1,1,~0|>"
            # Fields deliberately out of order to check parsing by name.
            "1<|box;c=0.5;h=800;w=1000;y2=800;x2=1000;y1=0;x1=500|>"
            "<|mask;x=0;y=0;c=0.5;data=1,1,~0|>"
        )
        regions = parse_output(output, "chair")
        self.assertEqual(len(regions), 2)
        self.assertAlmostEqual(regions[0]["score"], 0.9)
        self.assertBboxAlmostEqual(regions[0]["bbox"], [0.1, 0.25, 0.3, 0.5])
        self.assertAlmostEqual(regions[1]["score"], 0.5)
        self.assertBboxAlmostEqual(regions[1]["bbox"], [0.5, 0.0, 1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
