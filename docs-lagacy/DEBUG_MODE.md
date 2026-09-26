# Debug Mode

`config.json`의 `debug_mode`로 토론 런타임 진단 로그를 켜고 끕니다.

```json
{
  "web_mode": "live",
  "debug_mode": true
}
```

기본값은 `false`입니다. `true`인 세션에서는 브라우저가 SSE의 `debug` 이벤트를 세션 메모리에만 누적하고, 토론 종료 화면에서 **디버그 로그 JSON 받기** 버튼을 표시합니다. 서버 DB에는 저장하지 않습니다.

로그에는 Turn/phase/speaker/Persona, 실제 A/B 생성 모델과 control model, Turn Task/Action/target, 각 draft attempt, Action Fidelity/Stance/Turn Task Fidelity, State Patch, token usage가 포함됩니다.

`DEBATER_API_KEY`, `SESSION_SECRET`, Provider URL, signed `engine_token`은 포함하지 않습니다.
