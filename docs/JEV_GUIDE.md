# Jev Engineering & Architecture Playbook

คู่มือนี้นำแนวคิดเดิมเรื่อง Jev และ architectural combos กลับมาไว้ พร้อมแยกแนวทางที่เป็นเพียงตัวอย่างออกจากความสามารถที่มีใน Harness `0.7.1` จริง

> Harness ใช้ TypeSafe Jev API แบบ hosted เฉพาะเมื่อผู้ใช้เปิด `jev-public` อย่างชัดเจน ค่าเริ่มต้นของ schema-v3 เลือก context ในเครื่อง ไม่มี Jev แบบ local/edge, Gemini adapter, Exa, Cua หรือ `tools/jev-assistant.mjs` รวมมาให้ คอมโบด้านล่างจึงเป็น recipes สำหรับออกแบบ integration เพิ่ม ไม่ใช่คำสั่งว่าระบบติดตั้งไว้แล้ว

คู่มือ implementation ที่เป็นแหล่งอ้างอิงหลัก: [Jev runtime guide](../skills/best-in-code/references/jev-runtime.md) และ [async operation runtime](../skills/best-in-code/references/async-operation-runtime.md)

## 1. บทบาทของ Jev: ตัดสินใจแบบมีชนิดข้อมูล

Jev อยู่ข้าง LLM ที่เขียนคำตอบหรือโค้ด ไม่ได้มาแทน LLM นั้น Harness ส่ง state กับคำถามที่กำหนดขอบเขต แล้วตรวจ choice, score หรือ noul ก่อนใช้ผลตัดสินใจ

| ใช้ Jev กับ | อย่าใช้ผล Jev แทน |
| --- | --- |
| จัดประเภท, จัดอันดับ, เลือก tool/chunk จากตัวเลือกปิด, ตรวจเงื่อนไขเล็ก ๆ | ค้นข้อมูลสดหรืออ้าง API เวอร์ชันใหม่โดยไม่มีหลักฐาน |
| ให้คะแนนหรือประเมินข้อความจาก corpus ที่ส่งให้พิจารณา | การวิเคราะห์ยาว ๆ, การเขียนโค้ด, การอนุมัติ command หรือให้สิทธิ์ |
| กรองผลลัพธ์ที่มีหลักฐานกำกับ | การทดสอบจริง, verifier, authorization, policy หรือการตรวจผลข้างเคียง |

โน้ตต้นฉบับอ้าง latency ต่ำกว่า 200 ms และข้อควรระวังเรื่องคำตอบมั่นใจแต่ผิด ตัวเลข latency นั้นไม่ใช่ SLA หรือผลวัดของ Harness ส่วน confidence เป็นสัญญาณที่ใช้กับ threshold แบบกำหนดตายตัวได้ แต่ไม่ใช่หลักฐานว่าคำตอบจริงเสมอ

เวลาต้องถามเรื่องข้อมูลภายนอก ให้ค้นเอกสาร/API ก่อน แล้วให้ Jev เลือกระหว่างหลักฐานที่ได้มา อย่าให้ Jev เดาโครงสร้าง API จากความจำเพียงอย่างเดียว

## 2. คำถามตั้งต้นเรื่อง KV cache

คำถามจาก playbook เดิมคือ “จะออกแบบ coding agent อย่างไรถ้า LLM ไม่มี KV cache?” ใช้เป็นกรอบตรวจการสะสม transcript: ทุก turn กำลังส่ง context อะไรซ้ำ และงานไหนควรอ้างอิง state ที่มี digest แทนการ replay text เต็ม

การคิดต้นทุน route ต้องนับ context ที่ helper ต้องอ่านและ input ที่โมเดลหลักต้องอ่านหลังกลับมาด้วย ตัวเลข Opus/Sonnet 4.15 กับ 6.19 ในเอกสารต้นฉบับเป็นตัวอย่างราคาและสัดส่วน token ในอดีต ไม่ใช่ราคา ณ ปัจจุบันหรือผล Harness ใช้ `harness route-cost` กับ token/rate ที่ยืนยันแล้ว และปิด auto-switch ไว้

## 3. Architectural combos จาก playbook เดิม

คอมโบทั้งหมดนี้เป็นรูปแบบสำหรับวางระบบต่อยอด แต่ต้องติดตั้งและตรวจ backend แยกต่างหาก

### Jev + Exa หรือระบบค้นคว้าเว็บ

1. ใช้ search ดึงเอกสาร API, issue หรือ code sample ที่เกี่ยวข้อง
2. เก็บ URL/เวอร์ชัน/วันที่และแยกข้อเท็จจริงออกจากสมมติฐาน
3. ส่งเฉพาะผล public ที่จำเป็นให้ Jev จัดอันดับตาม task
4. ให้ LLM หลักสังเคราะห์คำตอบและตรวจข้อสรุปกับ source

Exa/Tavily เป็นชื่อจาก playbook เดิม ไม่ได้ต่ออยู่ใน Harness การส่งข้อมูลให้ search หรือ Jev ภายนอกต้องผ่าน data policy ของเจ้าของโปรเจกต์

### Jev + Gemini หรือ writer model อื่น

ตัวอย่างแนวคิดคือให้ writer model ทำแผน/โค้ด/คำอธิบาย ส่วน Jev ทำ micro-decisions เช่น relevance, visibility หรือเลือกหมวดจากตัวเลือกที่กำหนด ชื่อ Gemini 2.5 Pro/Flash, Claude Opus 4/Sonnet 4 และ GPT-4.5/o3 เป็นชื่อในโน้ตเก่า ไม่ใช่ binding ปัจจุบันหรือคำแนะนำด้านคุณภาพ/ราคา

Harness `0.7.0` มี Anthropic Messages adapter และ contract แบบ provider-neutral แต่ไม่มี Gemini หรือ general Codex API adapter โดยอัตโนมัติ Profile ใน contract ต้อง map กับ provider ที่ติดตั้งและตรวจ model/effort จริง

### Jev + Fast Jev Compaction

แนวคิดของ [`fast-jev-compaction`](https://github.com/tamaratran/fast-jev-compaction) คือรักษาคู่ tool call/result ให้สัมพันธ์กัน, คงข้อความล่าสุด, แล้วให้ Jev ช่วยตัดสินว่าผลเก่าควรเก็บเต็ม ย่อ หรือลบทิ้งจาก transcript ที่ส่งกลับ

Source ที่ตรวจใน Harness อยู่ที่ commit `e3f262a7f4d42bd8dd32ced30d26176f7cb545b0` หลักการที่นำมาใช้คือจับคู่ด้วย call ID และเก็บ full evidence ที่ durable ก่อนปรับ context ส่วน plugin นั้นไม่ได้เป็น dependency ของ Harness และผล Jev ที่ไม่แน่ใจไม่ควรทำให้ evidence สำคัญหายไป

ตัวอย่างเดิมเรื่อง `dotnet test` 1,847 tests และ project `KK` เป็นตัวอย่างจากอีกโปรเจกต์ ไม่ใช่ test suite หรือ benchmark ของ Harness

### Jev + Cua / Browser Use สำหรับงาน UI

แนวคิดคือให้ computer-use driver สังเกต DOM/accessibility tree หรือหน้าจอ แล้วให้ Jev เลือก action จาก element ที่พบจริง ก่อนให้ deterministic verifier ตรวจผล Cua และ Browser Use เป็น references จาก playbook ไม่ได้รวมอยู่ใน Harness package และผล vision/DOM ไม่ใช่ authorization สำหรับการซื้อ, จ่ายเงิน หรือลบข้อมูล

### Jev + Unreal Agent async operations

Unreal Agent แยก coordinator, durable operation manager และ session log เพื่อให้ long-running tools ทำงานเบื้องหลัง รับ user steering และกลับมาส่งผลภายหลัง แนวทางนี้เป็น architecture project แยก: Harness kernel รุ่นนี้ยังเรียก tools แบบ synchronous/sequential และไม่มี live inbox ระหว่าง run ดู [async operation guide](../skills/best-in-code/references/async-operation-runtime.md) ก่อนออกแบบ port

## 4. Repositories จากรายการเดิม

| Project | แนวคิด | สถานะใน Harness |
| --- | --- | --- |
| [Fast Jev Compaction](https://github.com/tamaratran/fast-jev-compaction) | รักษาคู่ tool call/result และลด transcript | ตรวจ source แล้ว; ไม่ได้ติดตั้งเป็น dependency |
| [CUA](https://github.com/trycua/cua) | computer-use drivers และ isolated environments | ยังไม่เชื่อมต่อ |
| [Browser Use](https://github.com/browser-use/browser-use) | browser observation/action loop | ยังไม่เชื่อมต่อ |
| [Exa JS](https://github.com/exa-labs/exa-js) | search/retrieval grounding | ยังไม่เชื่อมต่อ |
| [MCP Servers](https://github.com/modelcontextprotocol/servers) | backend tools ผ่าน MCP | ต้องเลือกและตรวจ server เป็นรายตัว |
| [Unreal Agent](https://github.com/unreallabsai/unreal-agent/tree/b7c9bf1c5c2fa4127255c07727a7c8413e23944a) | async-first coordinator และ durable operations | ตรวจ source ไว้; ยังไม่ได้ port |

ชื่อเหล่านี้เป็น shortlist เก่าที่เก็บกลับมา ไม่ใช่ผล security review ล่าสุด, endorsement หรือ runtime dependency

## 4.1 Cross-repository setup และ model matrix จากโน้ตเดิม

Harness ใช้ skill และ state files แบบ portable ข้าม provider ตัวอย่างคำสั่ง init จาก README ปัจจุบันคือ:

```bash
npx github:kingggg5/harness init --project . --models all
```

หลัง init ให้แก้ contract/profile ตาม provider ที่ติดตั้ง อย่าคิดว่าการตั้ง `READY` ใน config จะลงทะเบียน adapter หรือ service เอง

| กลุ่มในโน้ตเดิม | ตัวอย่างที่เคยยก | สถานะ/ข้อควรระวัง |
| --- | --- | --- |
| Writer/planner | Gemini 2.5 Pro/Flash (โน้ตเดิมกล่าวถึง context ใหญ่), Claude Opus 4/Sonnet 4, GPT-4.5/o3 | ชื่อและ model specs เป็น historical examples; ตรวจรุ่น, endpoint, privacy และราคาในปัจจุบันก่อน map profile |
| Local inference | Ollama, vLLM, DeepSeek R1 | ค่า provider API อาจไม่มี แต่ยังมี compute/hosting cost และความเสี่ยงด้าน data; Harness ไม่ได้ bundle local model adapter |
| Search grounding | Exa, Tavily | แนวคิดคือค้นเอกสารสดก่อน แล้วค่อยจัดอันดับหลักฐาน; ไม่ได้ติดตั้งใน Harness |
| Browser/computer use | Browser Use, CUA | เป็น external UI automation backends; ไม่ได้ติดตั้งใน Harness |

ราคา provider, context limit, capability และ data retention เปลี่ยนได้ ตัวอย่างข้างบนจึงไม่ใช่คำแนะนำให้เลือก model หรือยืนยัน compatibility

## 5. ใช้ CLI ที่มีจริงใน Harness

```bash
# Context query projection ในเครื่อง
node bin/harness.js turn-build --snapshot examples/jev-snapshot.json --query "Explain addition"

# Tiered tool catalog และ route-cost estimate
node bin/harness.js tools-disclose --registry skills/best-in-code/assets/templates/TOOL-REGISTRY.json --tier snippets
node bin/harness.js route-cost --input examples/jev-route-cost.json
```

การเลือก Jev API จาก `turn-build` ต้องใส่ `--jev-public --policy <TURN-POLICY.json>` และตั้ง `TYPESAFE_API_KEY` ใน environment คำสั่งจะปฏิเสธ chunk ที่ path ไม่ถูกจัดเป็น public; query ที่ส่งไปต้อง public ด้วย ดู runtime guide ก่อนส่งข้อมูลออกนอกเครื่อง

สำหรับ project ใหม่ คัดลอก `RUN-CONTRACT-JEV.json` ไปที่ `.harness/RUN-CONTRACT.json`, เติม Project/Run/task/verifier จริง แล้ว `harness run-validate` ก่อน `harness run` การใส่ `READY` ใน `CONFIG.md` หรือชื่อ combo ในคู่มือนี้ไม่ทำให้ backend ติดตั้งหรือเปิดใช้เอง

## 6. Best practices ที่เก็บมาจาก playbook เดิม

- Ground การตัดสินใจด้วย source จาก web/repository เมื่อโจทย์ถามข้อเท็จจริงภายนอก
- ใช้ choice/score ที่มีตัวเลือกและเกณฑ์ชัด แล้วตรวจผลตอบกลับด้วย schema/threshold
- ระบุว่าอะไรคือคำตอบจากโมเดล, อะไรคือหลักฐาน, และอะไรคือผลจาก deterministic verifier
- เก็บบรรทัด, error code, digest และ call ID ที่จำเป็น verbatim; ไม่ให้การย่อทำลายหลักฐาน
- ลด context หลังทราบ query; อย่าย่อล่วงหน้าแล้วทิ้งข้อมูลต้นฉบับถาวร
- อย่าอ้างว่าคอมโบช่วยประหยัดจนกว่าจะวัด input/cache/output tokens, pass rate และราคา provider กับ task ชุดเดียวกัน
