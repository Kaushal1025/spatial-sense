"""Tests for distance, step, and direction estimates.

Run from the repo root: python3 -m unittest discover -s server -p "test_*.py"
"""

import struct
import unittest

from server import geometry as g

SIZE = (640, 480)
HEIGHT = 1.78


def box(label, cx, cy, w, h, score=0.9):
    return {"label": label, "score": score, "bbox": [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]}


class GeometryTest(unittest.TestCase):
    def test_step_length(self):
        self.assertAlmostEqual(g.step_length_m(1.78), 0.7387, places=4)

    def test_distance_for_known_box(self):
        # focal = 320 / tan(32.5 deg) = 502.30 px; 502.30 * 1.7 / 200 = 4.27 m
        self.assertAlmostEqual(g.focal_px(640), 502.30, places=2)
        self.assertAlmostEqual(g.distance_m(200, 1.7, 640), 4.2696, places=3)

    def test_distance_zero_height_box(self):
        self.assertIsNone(g.distance_m(0, 1.7, 640))

    def test_angle_sign_and_rounding(self):
        self.assertEqual(g.angle_deg(0.5), 0)
        self.assertEqual(g.angle_deg(0.2), -20)  # -19.5
        self.assertEqual(g.angle_deg(0.8), 20)
        self.assertEqual(g.angle_deg(0.5 + 12.6 / 65), 15)
        self.assertEqual(g.angle_deg(0.5 + 12.4 / 65), 10)
        self.assertEqual(g.angle_deg(0.5 - 12.6 / 65), -15)

    def test_steps_rounding(self):
        self.assertEqual(g.steps(1.85, HEIGHT), 3)  # 2.50 steps
        self.assertEqual(g.steps(1.80, HEIGHT), 2)  # 2.44 steps
        self.assertEqual(g.steps(0.2, HEIGHT), 0)

    def test_direction_buckets(self):
        self.assertEqual(g.direction_words(0), "straight ahead")
        self.assertEqual(g.direction_words(-5), "straight ahead")
        self.assertEqual(g.direction_words(-10), "slightly left")
        self.assertEqual(g.direction_words(30), "slightly right")
        self.assertEqual(g.direction_words(35), "turn right about 35 degrees")
        self.assertEqual(g.direction_words(-35), "turn left about 35 degrees")

    def test_hand_vector_quadrants(self):
        hand = box("hand", 0.5, 0.5, 0.1, 0.1)["bbox"]
        cases = {
            (0.8, 0.2): "Move your hand up and to the right.",
            (0.2, 0.2): "Move your hand up and to the left.",
            (0.8, 0.8): "Move your hand down and to the right.",
            (0.2, 0.8): "Move your hand down and to the left.",
        }
        for (tx, ty), expected in cases.items():
            target = box("bottle", tx, ty, 0.1, 0.1)["bbox"]
            self.assertEqual(g.hand_guidance(hand, target), expected)

    def test_hand_a_little_threshold(self):
        hand = box("hand", 0.5, 0.5, 0.1, 0.1)["bbox"]
        target = box("bottle", 0.53, 0.2, 0.1, 0.1)["bbox"]
        self.assertEqual(g.hand_guidance(hand, target), "Move your hand up and a little to the right.")
        target = box("bottle", 0.2, 0.46, 0.1, 0.1)["bbox"]
        self.assertEqual(g.hand_guidance(hand, target), "Move your hand a little up and to the left.")
        # Exactly at the threshold is no longer "a little".
        target = box("bottle", 0.5 + 0.0625, 0.5 - 0.0625, 0.1, 0.1)["bbox"]
        self.assertEqual(g.hand_guidance(hand, target), "Move your hand up and to the right.")

    def test_image_size_jpeg(self):
        jpeg = (
            b"\xff\xd8"
            + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
            + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 480, 640) + b"\x00" * 10
        )
        self.assertEqual(g.image_size(jpeg), (640, 480))

    def test_image_size_png_and_unknown(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 320, 240)
        self.assertEqual(g.image_size(png), (320, 240))
        self.assertIsNone(g.image_size(b"not an image"))


# A person filling the frame height: 502.3 * 1.7 / 480 = 1.78 m, about 2.4 steps.
PERSON_AHEAD = box("person", 0.5, 0.5, 0.2, 1.0)


class ObstacleTest(unittest.TestCase):
    def items(self, regions):
        return [(r, g.measure(r, SIZE, HEIGHT)) for r in regions]

    def test_person_ahead_is_obstacle(self):
        self.assertEqual(g.measure(PERSON_AHEAD, SIZE, HEIGHT)["steps"], 2)
        message, region = g.obstacle_warning(self.items([PERSON_AHEAD]))
        self.assertIs(region, PERSON_AHEAD)
        self.assertEqual(message, "Obstacle ahead. Move left.")  # dead ahead, tie

    def test_side_with_fewer_objects(self):
        regions = [PERSON_AHEAD, box("table", 0.15, 0.6, 0.2, 0.2), box("car", 0.1, 0.4, 0.2, 0.2)]
        self.assertEqual(g.obstacle_warning(self.items(regions))[0], "Obstacle ahead. Move right.")
        regions = [PERSON_AHEAD, box("table", 0.85, 0.6, 0.2, 0.2)]
        self.assertEqual(g.obstacle_warning(self.items(regions))[0], "Obstacle ahead. Move left.")

    def test_tie_moves_away_from_obstacle(self):
        person = box("person", 0.35, 0.5, 0.2, 1.0)  # -10 degrees
        self.assertEqual(g.obstacle_warning(self.items([person]))[0], "Obstacle ahead. Move right.")

    def test_not_an_obstacle(self):
        far = box("person", 0.5, 0.5, 0.1, 0.3)
        off_to_side = box("person", 0.85, 0.5, 0.2, 1.0)  # 25 degrees
        bottle = box("bottle", 0.5, 0.5, 0.2, 1.0)
        self.assertIsNone(g.obstacle_warning(self.items([far, off_to_side, bottle])))
        # Without the user's height there are no steps, so no warning.
        self.assertIsNone(g.obstacle_warning([(PERSON_AHEAD, g.measure(PERSON_AHEAD, SIZE, None))]))


class GuidanceTest(unittest.TestCase):
    def test_nearest_object(self):
        regions = [box("door", 0.85, 0.4, 0.15, 0.5), box("chair", 0.2, 0.6, 0.2, 0.45)]
        self.assertEqual(g.build_guidance(regions, [], SIZE, HEIGHT), ["Chair, about 3 steps, slightly left."])

    def test_without_height_no_steps(self):
        regions = [box("chair", 0.2, 0.6, 0.2, 0.45)]
        self.assertEqual(g.build_guidance(regions, [], SIZE, None), ["Chair, slightly left."])

    def test_low_score_ignored(self):
        self.assertEqual(g.build_guidance([box("chair", 0.5, 0.5, 0.2, 0.4, score=0.1)], [], SIZE, HEIGHT), [])

    def test_obstacle_first_and_capped(self):
        regions = [PERSON_AHEAD, box("chair", 0.2, 0.6, 0.2, 0.45), box("bottle", 0.9, 0.5, 0.05, 0.1)]
        guidance = g.build_guidance(regions, ["bottle"], SIZE, HEIGHT)
        self.assertEqual(len(guidance), 2)
        self.assertEqual(guidance[0], "Obstacle ahead. Move left.")  # one object each side, tie
        self.assertTrue(guidance[1].startswith("Bottle, about"))

    def test_target_not_in_view(self):
        regions = [box("chair", 0.2, 0.6, 0.2, 0.45)]
        self.assertEqual(
            g.build_guidance(regions, ["frying pan"], SIZE, HEIGHT),
            ["Frying pan not in view. Turn slowly left or right.", "Chair, about 3 steps, slightly left."],
        )

    def test_target_in_reach_with_hand(self):
        bottle = box("bottle", 0.7, 0.4, 0.1, 0.4)  # about 0.7 m
        hand = box("hand", 0.4, 0.8, 0.1, 0.15)
        self.assertEqual(
            g.build_guidance([bottle, hand], ["bottle"], SIZE, HEIGHT),
            ["Move your hand up and to the right.", "Bottle, about 1 step, slightly right."],
        )

    def test_target_in_reach_without_hand(self):
        bottle = box("bottle", 0.5, 0.4, 0.1, 0.4)
        self.assertEqual(
            g.build_guidance([bottle], ["bottle"], SIZE, HEIGHT),
            [g.POINT_AT_HANDS, "Bottle, about 1 step, straight ahead."],
        )

    def test_far_target_skips_hand_guidance(self):
        bottle = box("bottle", 0.5, 0.4, 0.02, 0.05)  # about 5 m
        chair = box("chair", 0.2, 0.6, 0.2, 0.45)
        guidance = g.build_guidance([bottle, chair], ["bottle"], SIZE, HEIGHT)
        self.assertTrue(guidance[0].startswith("Bottle, about"))
        self.assertEqual(guidance[1], "Chair, about 3 steps, slightly left.")

    def test_step_label_is_spoken_as_step_edge(self):
        self.assertEqual(g.build_guidance([box("step", 0.5, 0.9, 0.4, 0.1)], [], SIZE, HEIGHT)[0][:15], "Step edge, abou")

    def test_annotate_adds_fields(self):
        [region] = g.annotate([box("chair", 0.2, 0.6, 0.2, 0.45)], SIZE, HEIGHT)
        self.assertEqual(region["steps"], 3)
        self.assertEqual(region["angle_deg"], -20)
        self.assertAlmostEqual(region["distance_m"], 2.09, places=2)
        self.assertEqual(region["label"], "chair")


if __name__ == "__main__":
    unittest.main()
