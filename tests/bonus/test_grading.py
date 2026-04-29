"""Tests for app.bonus.calculator.grading."""

from decimal import Decimal

from app.bonus.calculator.grading import find_grade, parse_grades


GRADES_RAW = [
    {"from": 70, "to": 79, "value": 80000},
    {"from": 80, "to": 84, "value": 100000},
    {"from": 85, "to": 89, "value": 130000},
    {"from": 90, "to": 97, "value": 150000},
    {"from": 98, "to": 100, "value": 170000},
]


class TestFindGrade:
    def setup_method(self):
        self.grades = parse_grades(GRADES_RAW)

    # TC-60
    def test_70_in_70_79(self):
        g = find_grade(self.grades, Decimal("70"))
        assert g.from_percent == Decimal("70")

    def test_79_in_70_79(self):
        g = find_grade(self.grades, Decimal("79"))
        assert g.from_percent == Decimal("70") and g.to_percent == Decimal("79")

    def test_80_in_80_84(self):
        g = find_grade(self.grades, Decimal("80"))
        assert g.from_percent == Decimal("80")

    def test_87_in_85_89(self):
        g = find_grade(self.grades, Decimal("87"))
        assert g.value == Decimal("130000")

    def test_90_in_90_97(self):
        g = find_grade(self.grades, Decimal("90"))
        assert g.value == Decimal("150000")

    def test_97_in_90_97(self):
        g = find_grade(self.grades, Decimal("97"))
        assert g.value == Decimal("150000")

    def test_98_in_98_100(self):
        g = find_grade(self.grades, Decimal("98"))
        assert g.value == Decimal("170000")

    def test_100_in_98_100(self):
        g = find_grade(self.grades, Decimal("100"))
        assert g.value == Decimal("170000")

    def test_69_below_min(self):
        assert find_grade(self.grades, Decimal("69")) is None

    def test_zero(self):
        assert find_grade(self.grades, Decimal("0")) is None

    # TC-61: Hole between grades — 89.5 → ceil(89.5) = 90 → grade 90-97
    def test_89_5_via_ceil_lands_in_90_97(self):
        g = find_grade(self.grades, Decimal("89.5"))
        assert g.from_percent == Decimal("90") and g.to_percent == Decimal("97")

    def test_79_5_via_ceil_lands_in_80_84(self):
        g = find_grade(self.grades, Decimal("79.5"))
        assert g.from_percent == Decimal("80")

    def test_90_8_via_ceil_lands_in_91_then_grade_90_97(self):
        # avg from TC-02
        g = find_grade(self.grades, Decimal("90.80"))
        assert g.value == Decimal("150000")
