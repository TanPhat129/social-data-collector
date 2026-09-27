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


def test_tutor_service_advertisement_is_not_a_tutor_demand():
    content = """Bạn đang tìm gia sư Tiếng Anh 1:1?
Kèm từ căn bản đến giao tiếp. Ôn thi chứng chỉ theo lộ trình.
Nhận học sinh lớp 1-12. Chỉ 600k/tháng – học thử hoàn toàn miễn phí."""
    assert TutorIntentClassifier().classify(content).intent == "TUTOR_OFFER"
