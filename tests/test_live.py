from tx5dr_device_panel.live import _is_ptt_active


def test_live_tx_refresh_uses_only_real_ptt_state():
    assert _is_ptt_active({"radio": {"ptt": True, "tx": False}, "ft8": {"currentTx": {"active": False}}})
    assert not _is_ptt_active({"radio": {"ptt": False, "tx": True}, "ft8": {"currentTx": {"active": True}}})
