import unittest

from boxscore import parse_boxscore, parse_boxscore_messages, format_boxscore_message


SAMPLE = """[CHI 3 @ MIA 13 · Week 14](https://example.com/game)
<:mt_chi:123> CHI Bears 3 · McTraherMadden · 4-9-0
<:mt_mia:456> MIA **Dolphins** 13 · benroastemburger · 4-9-0
[Box score](https://example.com/game)
CHI
Caleb Williams
16/30, 248 yds, 2 INT
MIA
Malik Willis
17/26, 159 yds, 1 TD
"""


class RecordsTest(unittest.TestCase):
    def test_records_and_stats_reach_photo_caption(self):
        box = parse_boxscore(SAMPLE)
        self.assertEqual((box.away_record, box.home_record), ("4-9-0", "4-9-0"))
        self.assertEqual(box.away_stats[0].name, "Caleb Williams")
        self.assertEqual(box.home_stats[0].name, "Malik Willis")
        self.assertIn("Records: CHI 4-9-0 · MIA 4-9-0", format_boxscore_message(box, "", True))
        self.assertNotIn("Records:", format_boxscore_message(box, "", False))

    def test_linked_emoji_and_joined_summaries(self):
        text = SAMPLE.replace("<:mt_chi:123>", "[:mt_chi:](https://example.com/chi)")
        text = text.replace("\n<:mt_mia:456>", " [:mt_mia:](https://example.com/mia)")
        box = parse_boxscore(text)
        self.assertEqual((box.away_record, box.home_record), ("4-9-0", "4-9-0"))

    def test_old_message_without_records(self):
        box = parse_boxscore("CHI 3 @ MIA 13 · Week 14\nBox score\nCHI\nMIA")
        self.assertEqual((box.away_record, box.home_record), (None, None))
        self.assertNotIn("Records:", format_boxscore_message(box, ""))

    def test_partial_record_does_not_invent_other_team(self):
        box = parse_boxscore(SAMPLE.replace(" · benroastemburger · 4-9-0", ""))
        self.assertEqual((box.away_record, box.home_record), ("4-9-0", None))
        self.assertIn("Records: CHI 4-9-0\n", format_boxscore_message(box, ""))

    def test_multiple_games_keep_their_records(self):
        second = SAMPLE.replace("Week 14", "Week 15").replace("4-9-0", "5-9-0")
        boxes = parse_boxscore_messages(SAMPLE + "\n" + second)
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0].away_record, "4-9-0")
        self.assertEqual(boxes[1].away_record, "5-9-0")


if __name__ == "__main__":
    unittest.main()
