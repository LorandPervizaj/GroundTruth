"""Parser services and corpus filters share one version registry."""

from groundtruth.analytics.corpus_filters import ACTIVE_PARSER_VERSIONS
from groundtruth.services.merrjep_parsing import PARSER_VERSION as merrjep_version
from groundtruth.services.myrealestate_parsing import PARSER_VERSION as myrealestate_version
from groundtruth.services.parsing import PARSER_VERSION as gjirafa_version
from groundtruth.services.pro_rks_parsing import PARSER_VERSION as pro_rks_version
from groundtruth.services.topia_parsing import PARSER_VERSION as topia_version
from groundtruth.services.vision_parsing import PARSER_VERSION as vision_version
from groundtruth.versions import PARSER_VERSIONS


def test_all_parser_services_use_registry_versions() -> None:
    service_versions = {
        "gjirafa": gjirafa_version,
        "merrjep": merrjep_version,
        "pro-rks": pro_rks_version,
        "vision": vision_version,
        "topia": topia_version,
        "myrealestate": myrealestate_version,
    }
    assert service_versions == PARSER_VERSIONS
    assert set(ACTIVE_PARSER_VERSIONS) == set(PARSER_VERSIONS.values())
