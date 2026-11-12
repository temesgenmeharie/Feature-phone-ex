"""Phase 4 tests: Simulated Feature Phone profiles and fault injection."""

import pytest

from app.serial.engine import ATCommandEngine
from app.serial.transport import SerialTransportError
from app.simulator.transport import SimulatedSerialTransport


def test_simulator_full_profile_at_responses():
    sim = SimulatedSerialTransport.from_profile_id("nokia_105_lab")
    engine = ATCommandEngine(sim)
    engine.open()

    assert engine.send_command("AT").is_ok
    assert engine.send_command("AT+GMI").body_lines == ["Nokia"]
    assert engine.send_command("AT+GMM").body_lines == ["Nokia 105 (TA-1174)"]
    assert engine.send_command("AT+GSN").body_lines == ["358912094512345"]
    assert engine.send_command("AT+CPBS=?").body_lines == ['+CPBS: ("SM","ME","MC","RC","DC")']

    assert engine.send_command('AT+CPBS="MC"').is_ok
    mc = engine.send_command("AT+CPBR=1,50")
    assert mc.is_ok
    assert len(mc.body_lines) == 2

    assert engine.send_command("AT+CMGF=1").is_ok
    assert engine.send_command('AT+CPMS="ME"').is_ok
    sms = engine.send_command('AT+CMGL="ALL"')
    assert sms.is_ok
    assert any("Meeting moved to Room 204" in ln for ln in sms.body_lines)
    engine.close()


def test_simulator_limited_profile_and_fault_injection():
    sim = SimulatedSerialTransport.from_profile_id("itel_limited_modem")
    engine = ATCommandEngine(sim)
    engine.open()

    assert engine.send_command("AT+GMI").body_lines == ["Itel"]
    assert engine.send_command("AT+CPBS=?").terminal_status == "ERROR"
    assert engine.send_command("AT+CPMS=?").terminal_status == "ERROR"

    sim.simulate_timeout = True
    assert engine.send_command("AT").terminal_status == "TIMEOUT"
    sim.simulate_timeout = False

    sim.simulate_disconnect = True
    with pytest.raises(SerialTransportError):
        engine.send_command("AT")
    engine.close()
