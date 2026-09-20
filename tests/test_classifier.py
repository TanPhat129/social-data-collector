from app.processing.classifier import TutorIntentClassifier
from app.processing.keyword_filter import KeywordFilter


def test_tuyen_gia_su_is_a_tutor_demand():
    content = "Cần tuyển gia sư Toán lớp 8 tại Quận 3"
    assert KeywordFilter(["tuyển gia sư"]).matches(content)
    assert TutorIntentClassifier().classify(content).intent == "FIND_TUTOR"


def test_gs_abbreviation_is_a_tutor_demand():
    content = "Cần tìm gs lớp 2, 3 môn Tân Hiệp BD. Gs nhận lớp ib"
    assert KeywordFilter(["cần tìm gs"]).matches(content)
    assert TutorIntentClassifier().classify(content).intent == "FIND_TUTOR"
