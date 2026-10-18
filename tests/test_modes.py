import numpy as np

from mnemo import modes
from mnemo.data import Mixture, ShardWriter
from mnemo.trainer import topic_of


def test_every_mode_is_complete():
    assert len(modes.MODES) >= 5
    for k, m in modes.MODES.items():
        assert m["seeds"] and m["blurb"] and m["icon"]
        for preset in ("starter", "standard", "large"):
            assert "wikipedia" in m["library"][preset]  # every mode keeps learning basic language


def test_topic_of_shards():
    assert topic_of("web-code") == "code"
    assert topic_of("gutenberg") == "literature"
    assert topic_of("web") == "general"
    assert topic_of("actions") == "general"


def test_mode_boosts_matching_data(tmp_path):
    lib, web = tmp_path / "lib", tmp_path / "web"
    ShardWriter(lib, "wikipedia").append(np.arange(10000) % 500)
    ShardWriter(lib, "code").append(np.arange(10000) % 500)
    ShardWriter(web, "web-code").append(np.arange(5000) % 500)
    mix = Mixture({"library": lib, "web": web}, {"library": 0.5, "web": 0.5}, topic_of=topic_of, mode="general")
    w = mix.source_weights()
    assert abs(w[("library", "code")] - w[("library", "wikipedia")]) < 1e-9
    mix.mode = "code"
    w = mix.source_weights()
    assert abs(w[("library", "code")] - 5 * w[("library", "wikipedia")]) < 1e-9
    assert mix.batch(4, 32, "cpu") is not None


def test_link_scoring_and_page_filter():
    assert modes.link_score("code", "https://docs.python.org/3/library/os.html", "docs.python.org") > \
        modes.link_score("code", "https://example.com/recipes", "example.com")
    prose = "word " * 200
    assert modes.page_ok("general", "<p></p>", prose)
    assert not modes.page_ok("code", "<p></p>", prose)  # code mode needs code on the page
    assert modes.page_ok("code", "<pre>x</pre><code>y</code>", prose)
