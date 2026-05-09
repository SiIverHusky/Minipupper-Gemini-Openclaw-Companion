# Testing & Validation Plan

**Last Updated:** 2026-05-09  
**Version:** 0.1 Alpha  
**Owner:** Minipupper Team

---

## 1. Testing Overview

This document outlines comprehensive testing strategy for Minipupper Operator, including unit tests, integration tests, and system-level validation.

### Testing Pyramid

```
                    ▲
                   /│\
                  / │ \
                 /  │  \  System Tests (3-5 tests)
                /   │   \ End-to-end scenarios
               /    │    \
              ╱─────┼─────╲
             /      │      \
            /   Integration  \  Integration Tests (10-15 tests)
           /         │         \ Full conversation flow
          ╱──────────┼──────────╲
         /           │           \
        /    Unit Tests (20-30)   \
       /      Individual modules   \
      ╱──────────────┼──────────────╲
     ────────────────────────────────────

      Bottom: Most tests, fast execution
      Top: Fewest tests, comprehensive coverage
```

---

## 2. Unit Tests (Phase 1)

### 2.1 Audio Module Tests

**Module:** `src/audio/barge_in_detector.py`

| Test ID | Test Case | Input | Expected Output | Status |
|---------|-----------|-------|-----------------|--------|
| AU-001 | Detector initialization | Config object | Detector active | ⏳ TODO |
| AU-002 | Speech detection | Loud audio (energy > 500) | `on_barge_in()` called | ⏳ TODO |
| AU-003 | Noise rejection | Soft noise (energy < 500) | No interrupt | ⏳ TODO |
| AU-004 | Silence debounce | Brief pause in speech | No reset | ⏳ TODO |
| AU-005 | Energy calculation | Audio chunk | Correct RMS | ⏳ TODO |

**Test Commands:**
```bash
python -m pytest tests/unit/test_barge_in_detector.py -v
```

**Module:** `src/audio/audio_manager.py`

| Test ID | Test Case | Input | Expected Output | Status |
|---------|-----------|-------|-----------------|--------|
| AU-006 | ASR initialization | Config | Whisper model loaded | ⏳ TODO |
| AU-007 | TTS initialization | Config | TTS client ready | ⏳ TODO |
| AU-008 | Audio interruption | Speak + barge-in | Returns False | ⏳ TODO |
| AU-009 | Audio completion | Speak (no interrupt) | Returns True | ⏳ TODO |

### 2.2 Core Logic Tests

**Module:** `src/core/task_queue.py`

| Test ID | Test Case | Input | Expected Output | Status |
|---------|-----------|-------|-----------------|--------|
| CO-001 | Queue creation | - | All queues initialized | ⏳ TODO |
| CO-002 | Put/Get operations | Item | Item retrieved | ⏳ TODO |
| CO-003 | Queue timeout | Full queue | Timeout exception | ⏳ TODO |
| CO-004 | Thread safety | Multiple threads | No data loss | ⏳ TODO |
| CO-005 | Get latest | Old + new items | Only latest returned | ⏳ TODO |

### 2.3 Configuration Tests

**Module:** `config/config.yaml` loading

| Test ID | Test Case | Input | Expected Output | Status |
|---------|-----------|-------|-----------------|--------|
| CF-001 | Load valid config | config.yaml | Dict with all sections | ⏳ TODO |
| CF-002 | Load .env variables | .env file | Environment vars set | ⏳ TODO |
| CF-003 | Missing key handling | Partial config | Defaults applied | ⏳ TODO |

---

## 3. Integration Tests (Phase 2)

### 3.1 Audio Pipeline

**Test:** `IT-001: ASR → Operator → TTS Flow`

**Scenario:**
```
1. User speaks: "Stand up"
   ↓
2. ASR transcribes to text
   ↓
3. Text placed in input_text_queue
   ↓
4. Operator processes input
   ↓
5. Response placed in output_text_queue
   ↓
6. TTS generates and plays audio
```

**Validation:**
- ✓ Text matches speech content (ASR accuracy)
- ✓ Response is coherent (Operator logic)
- ✓ Audio plays without errors

**Test Script Location:** `tests/integration/test_conversation_flow.py`

**Expected Duration:** ~30 seconds per test

---

### 3.2 Barge-in Integration

**Test:** `IT-002: Barge-in During Speech`

**Scenario:**
```
1. Robot starts speaking response
2. Detector starts monitoring
3. After 1 second, user speaks over robot
4. Detector signals interrupt
5. Robot stops mid-sentence
6. User input processed
```

**Validation:**
- ✓ Detector activated during speech
- ✓ Interrupt latency < 500ms
- ✓ TTS playback stops cleanly
- ✓ New user input accepted

**Test Script Location:** `tests/integration/test_barge_in_integration.py`

**Expected Duration:** ~60 seconds per test

---

### 3.3 Movement Commands

**Test:** `IT-003: Movement Command Execution`

**Scenario:**
```
1. User says: "Move forward"
   ↓
2. Operator generates command
   ↓
3. Movement queued
   ↓
4. Movement worker executes
   ↓
5. Robot moves forward
```

**Validation:**
- ✓ Command recognized correctly
- ✓ Movement queue populated
- ✓ Motor control invoked
- ✓ Status updates received

**Test Script Location:** `tests/integration/test_movement.py`

---

### 3.4 Error Handling

**Test:** `IT-004: Graceful Degradation`

**Scenarios:**
1. **TTS Failure** - ASR works, TTS fails
   - Expected: Log error, continue listening
   
2. **ASR Timeout** - No speech detected for 30 seconds
   - Expected: Reset, broadcast timeout status
   
3. **Queue Overflow** - Queue fills up
   - Expected: Drop old items, prevent deadlock
   
4. **Worker Crash** - One worker thread dies
   - Expected: Other workers continue, log error

**Test Script Location:** `tests/integration/test_error_handling.py`

---

## 4. System Tests (Phase 3)

### 4.1 Long-Running Stability

**Test:** `ST-001: 24-Hour Stability Run`

**Setup:**
- Run operator continuously for 24 hours
- Log all events, errors, resource usage
- Simulate periodic user interactions

**Metrics:**
- Memory growth (should be < 5% per hour)
- CPU usage (should be < 50% average)
- Error count (should be < 1 per hour)
- Queue depth (should be < 10 items)

**Success Criteria:**
- Zero crashes
- Stable performance throughout
- All worker threads alive

**Test Duration:** 24 hours wall-clock time

---

### 4.2 Concurrency Stress Test

**Test:** `ST-002: High-Concurrency Handling`

**Setup:**
- Simulate rapid user interactions
- Multiple simultaneous movements
- Queue stress (10+ items/second)

**Metrics:**
- Response latency (p95, p99)
- Queue depth at peak
- Memory usage spike

**Success Criteria:**
- No deadlocks
- Latency stays < 2s (p95)
- No data loss

---

### 4.3 Network Failure Scenarios

**Test:** `ST-003: Tailscale Network Resilience`

**Scenarios:**
1. **Network Down** - Disconnect from cloud gateway
   - Expected: App continues locally, logs network error
   
2. **Partial Network** - High latency connection
   - Expected: Retry logic works, doesn't block local operation
   
3. **Network Restore** - Connection restored after dropout
   - Expected: Syncs state, resumes cloud features

**Success Criteria:**
- Local operation unaffected by network issues
- Graceful degradation, not hard failure
- State consistency after reconnect

---

## 5. Test Environment Setup

### 5.1 Local Development Environment

```bash
# Create test venv
python -m venv venv_test
source venv/bin/activate

# Install dependencies + test tools
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-timeout

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/unit/test_barge_in_detector.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### 5.2 Minipupper Hardware Testing

**Prerequisites:**
- Minipupper robot (Debian-based Raspberry Pi)
- Microphone + speakers connected
- SSH access configured
- Tailscale connected to network

**Setup:**
```bash
# On Minipupper:
ssh minipupper@192.168.1.100

# Clone and setup
cd /home/minipupper
git clone [repo-url]
cd minipupper-app
python -m pip install -r requirements.txt
cp config/.env.sample config/.env
# Edit .env with credentials

# Run operator
python minipupper_operator.py
```

---

## 6. Test Checklist

### Before First Release (Beta)

**Audio & Speech**
- [ ] ASR works with local model (no internet)
- [ ] TTS works (Google Cloud or Piper)
- [ ] Barge-in detects user speech reliably
- [ ] Barge-in false positive rate < 1%
- [ ] No audio glitches or dropouts

**Operator Logic**
- [ ] Response generation works
- [ ] Conversation history tracked
- [ ] Timeout handling correct
- [ ] Error messages helpful

**Movement**
- [ ] All movement commands execute
- [ ] Safety limits respected
- [ ] Status updates accurate
- [ ] Motor errors handled gracefully

**System**
- [ ] Startup/shutdown clean
- [ ] Graceful restart works
- [ ] Logs capture all events
- [ ] Configuration hot-reload (if implemented)

**Network**
- [ ] Tailscale connection stable
- [ ] Fallback to local network works
- [ ] Cloud features optional (not required for core operation)

---

## 7. Known Issues & Limitations

### Current Known Issues
- [ ] LLM response generation not yet implemented
- [ ] Movement APIs not yet integrated
- [ ] VAD (Voice Activity Detection) not implemented (using energy-based only)
- [ ] No multi-language support yet

### Workarounds
1. **LLM:** Use placeholder responses until LLM integrated
2. **Movement:** Use mock movement functions for testing
3. **VAD:** Tune energy threshold for your environment
4. **Language:** English only for now

---

## 8. Test Execution Timeline

| Phase | Start Date | Duration | Deliverable |
|-------|-----------|----------|-------------|
| Unit Tests | 2026-05-10 | 2 days | Unit test suite |
| Integration Tests | 2026-05-12 | 4 days | Integration test suite |
| System Tests | 2026-05-16 | 5 days | System test results |
| Bug Fixes | 2026-05-21 | 3 days | Bug fixes applied |
| Beta Release | 2026-05-24 | - | Beta ready |

---

## 9. Regression Testing

After each change, run this minimum set:

```bash
# Quick regression test suite (~5 minutes)
pytest tests/unit/ -v -k "not slow"
pytest tests/integration/test_conversation_flow.py -v
pytest tests/integration/test_barge_in_integration.py -v
```

---

## 10. Test Results Documentation

After each test run, update:

**File:** `docs/TEST_RESULTS.md`

**Template:**
```markdown
## Test Run 2026-05-10

**Environment:** Raspberry Pi 4 8GB, Debian 11, Python 3.9

### Summary
- Unit Tests: 25/25 passed ✓
- Integration Tests: 12/15 passed (3 skipped due to hardware)
- System Tests: Pending

### Failures
(List any failures with error details)

### Notes
(Any observations or anomalies)
```

---

**Last Updated:** 2026-05-09  
**Next Review:** 2026-05-10 (after unit test implementation starts)
