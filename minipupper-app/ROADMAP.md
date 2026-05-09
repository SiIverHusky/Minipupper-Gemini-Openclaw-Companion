# Development Roadmap - Minipupper Operator

**Status:** Early Planning (Updated 2026-05-09)  
**Vision:** Autonomous voice-first AI assistant for Minipupper robots

---

## Phase 1: Foundation & Audio (May 2026)
**Duration:** 2 weeks | **End Date:** 2026-05-23  
**Owner:** Core Team

### Milestones
- **2026-05-10:** Audio pipeline complete
  - ✅ Barge-in detector framework (done)
  - ⏳ ASR/TTS integration (Whisper + Google Cloud)
  - ⏳ Audio device selection & testing
  
- **2026-05-15:** End-to-end audio tests
  - ⏳ Unit tests for barge-in (50+ test cases)
  - ⏳ Integration tests for conversation flow
  - ⏳ Hardware audio validation
  
- **2026-05-20:** Optimization & tuning
  - ⏳ Barge-in threshold calibration for production
  - ⏳ Latency profiling (goal: < 500ms)
  - ⏳ Memory profiling (goal: < 200MB)

### Success Criteria
- [ ] Barge-in latency < 500ms average
- [ ] ASR accuracy > 95% in clean environment
- [ ] TTS quality acceptable (Google Cloud baseline)
- [ ] Zero audio glitches in 1-hour test run
- [ ] Energy threshold auto-calibration working

---

## Phase 2: Operator Logic (June 2026)
**Duration:** 2-3 weeks | **End Date:** 2026-06-10  
**Owner:** AI/Logic Team

### Milestones
- **2026-05-25:** LLM Integration
  - ⏳ Evaluate local vs cloud LLM (Ollama vs Gemini)
  - ⏳ Implement response generation worker
  - ⏳ System prompt design for autonomous operation
  
- **2026-06-01:** Conversation Management
  - ⏳ Context window management (8K tokens)
  - ⏳ Conversation history tracking
  - ⏳ Intent classification (delegate to movement vs conversation)
  
- **2026-06-10:** Integration Testing
  - ⏳ Full conversation flow tests
  - ⏳ Multi-turn dialogue validation
  - ⏳ Error recovery testing

### Success Criteria
- [ ] LLM response latency < 3 seconds (small model)
- [ ] Conversation context preserved across turns
- [ ] Intent classification accuracy > 90%
- [ ] Zero infinite loops or hang conditions
- [ ] Graceful handling of LLM timeouts

### Technical Decisions Pending
- **Local vs Cloud LLM:**
  - Option A: Ollama (local, no internet needed, slower)
  - Option B: Google Gemini (cloud, fast, requires internet)
  - Option C: Hybrid (local fallback to cloud)
  - **Decision:** TBD by 2026-05-25

- **Context Strategy:**
  - Sliding window (keep last N messages)
  - Summarization (compress old messages)
  - Hierarchical (important messages preserved)
  - **Decision:** TBD by 2026-06-01

---

## Phase 3: Robot Control (July 2026)
**Duration:** 3 weeks | **End Date:** 2026-07-01  
**Owner:** Robotics Team

### Milestones
- **2026-06-15:** Movement API Development
  - ⏳ Map voice commands to motor control (sit, stand, move, turn, etc.)
  - ⏳ Implement safety limits (speed, acceleration, collision avoidance)
  - ⏳ Status feedback from motors
  
- **2026-06-22:** Sensor Integration
  - ⏳ IMU-based pose estimation
  - ⏳ Distance sensors for obstacle detection
  - ⏳ Battery level monitoring
  
- **2026-07-01:** Hardware Validation
  - ⏳ End-to-end movement tests
  - ⏳ Voice command interpretation
  - ⏳ Safety validation

### Success Criteria
- [ ] All basic movements work (sit, stand, forward, backward, turn)
- [ ] Movement response latency < 500ms
- [ ] Safety limits enforced (no collision)
- [ ] Sensor feedback integrated
- [ ] Battery level reported accurately

### Needs from Reference
- [ ] Existing movement API code (from reference/api/move_api.py)
- [ ] Motor control library/documentation
- [ ] Safety protocols/constraints
- [ ] Current sensor calibration values

---

## Phase 4: Production Hardening (July-August 2026)
**Duration:** 4 weeks | **End Date:** 2026-08-15  
**Owner:** Full Team

### Milestones
- **2026-07-10:** Performance Optimization
  - ⏳ Memory leak detection & fixes
  - ⏳ CPU usage optimization
  - ⏳ Battery consumption analysis
  
- **2026-07-25:** Stress Testing
  - ⏳ 72-hour continuous operation test
  - ⏳ High-concurrency load testing
  - ⏳ Network failure scenarios
  
- **2026-08-01:** Documentation Complete
  - ⏳ User guide for Minipupper operators
  - ⏳ Troubleshooting guide
  - ⏳ Configuration reference
  
- **2026-08-15:** Beta Release
  - ⏳ Release v0.1.0-beta
  - ⏳ Deployment scripts ready
  - ⏳ Monitoring/alerting setup

### Success Criteria
- [ ] 72-hour test run without crashes
- [ ] Memory stable (no growth > 10%)
- [ ] CPU usage < 60% average
- [ ] Response latency stable (no degradation)
- [ ] All major documentation complete

---

## Phase 5: Advanced Features (September 2026+)
**Duration:** TBD  
**Owner:** Feature Team

### Potential Enhancements (Priority Order)

**High Priority:**
1. **Multi-user Support** - Different users, voice identification
2. **Voice Activity Detection (VAD)** - ML-based speech detection
3. **Gesture Recognition** - Combine with hand gestures (facial-expression-app)
4. **Cloud Logging** - Remote monitoring & debugging
5. **Scheduled Tasks** - "Remind me in 10 minutes"

**Medium Priority:**
6. **Multi-language Support** - Spanish, Chinese, Japanese
7. **Custom Wake Word** - Instead of always listening
8. **Conversation Recording** - For debugging & improvement
9. **A/B Testing Framework** - Test different LLM prompts
10. **Performance Analytics** - Latency tracking, optimization

**Lower Priority:**
11. **Vision Integration** - Camera-based tasks
12. **Web Dashboard** - Remote monitoring
13. **Mobile App** - Control via smartphone
14. **Voice Cloning** - Custom voice personality
15. **Emotional Recognition** - Adapt to user mood

### Expansion Points (Documented)
Each feature has expansion points documented in [ARCHITECTURE.md](docs/ARCHITECTURE.md#7-expansion-points):
- How to add new movements
- How to add new sensors
- How to add new LLM providers
- How to add new audio engines

---

## Cross-Phase Considerations

### Testing Throughout
Every phase includes testing:
- **Unit Tests:** Individual modules
- **Integration Tests:** Component interactions
- **System Tests:** End-to-end flows
- **Hardware Tests:** Minipupper-specific validation
- **Stress Tests:** High-load scenarios

See [TESTING_PLAN.md](docs/TESTING_PLAN.md) for detailed test strategy.

### Documentation Throughout
All development is accompanied by dated documentation:
- **PROGRESS.md** - Development log
- **ARCHITECTURE.md** - System design
- **BARGE_IN_GUIDE.md** - Feature details
- **TESTING_PLAN.md** - Test strategy
- **DEPLOYMENT_GUIDE.md** - Operations guide

### Deployment Readiness
- **Phase 1-2:** Internal testing only (not on robot)
- **Phase 3:** Hardware testing (controlled environment)
- **Phase 4:** Beta deployments (select team members)
- **Phase 5:** Production (public release)

---

## Resource Requirements

### Hardware
- 1x Minipupper robot (dev/test)
- 1x Raspberry Pi 4 8GB (alternate hardware testing)
- USB TPU or GPU (optional, for accelerated inference)

### Team
- 1x Audio/ML engineer (Phase 1-2)
- 1x Roboticist (Phase 3)
- 1x DevOps/QA (Phase 4)
- 1x Documentation lead (all phases)

### Infrastructure
- Git repository (private)
- CI/CD pipeline (GitHub Actions or similar)
- Logging/monitoring (optional, for Phase 4+)
- Bug tracking system

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| LLM latency too high | High | Start with small model, use local Ollama |
| Barge-in false positives | Medium | Extensive tuning, VAD integration in Phase 5 |
| Memory leaks | High | Continuous monitoring, stress testing Phase 4 |
| Hardware compatibility | High | Test on Minipupper early & often |
| Internet dependency | Medium | Design for offline operation (local LLM) |
| Security (credentials) | Medium | Use environment variables, rotate keys regularly |

---

## Success Metrics (At Each Phase End)

**Phase 1 Complete = ✓**
- Barge-in latency < 500ms
- Audio pipeline stable for 24 hours
- All audio unit tests passing

**Phase 2 Complete = ✓**
- LLM responses < 5 seconds
- Conversation context working
- Intent classification > 90% accuracy

**Phase 3 Complete = ✓**
- All movement commands functional
- Safety limits enforced
- Hardware integration tested

**Phase 4 Complete = ✓**
- 72-hour stability test passed
- No crashes or memory leaks
- Documentation complete

**Production Ready = ✓**
- All above + advanced features as needed
- User documentation excellent
- Deployment scripts automated
- Monitoring in place

---

## Quick Reference: Key Dates

| Date | Milestone | Deliverable |
|------|-----------|-------------|
| 2026-05-09 | Project Start | Project structure + docs |
| 2026-05-15 | Audio Phase 1 | ASR/TTS integration |
| 2026-05-23 | Audio Phase 2 | Full audio pipeline tested |
| 2026-06-10 | Operator Phase | LLM integration complete |
| 2026-07-01 | Robot Control | Movement API integrated |
| 2026-08-15 | Beta Release | v0.1.0-beta ready |
| 2026-09-01 | Advanced Features | Phase 5 planning |

---

## Feedback & Iteration

**Quarterly Reviews:**
- **End of May:** Audio phase review
- **End of June:** Operator phase review
- **End of July:** Robot control review
- **Mid-August:** Release readiness review

**Update This Document:**
- Monthly: Add completed milestones
- Monthly: Update risk assessment
- As needed: Adjust timeline based on progress
- Before phase end: Confirm success criteria

---

**Roadmap Version:** 1.0  
**Last Updated:** 2026-05-09  
**Next Update:** 2026-05-20 (mid-phase 1)

For questions or updates, contact the Minipupper Team.
