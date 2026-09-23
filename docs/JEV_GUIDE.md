# Jev ใน Harness

คู่มือนี้อธิบายวิธีใช้ Jev decision runtime ที่มีอยู่จริงใน Harness `0.7.0` ไม่ใช่รายการ integration ที่วางแผนไว้

Harness แบ่งหน้าที่เป็น LLM สำหรับวิเคราะห์และเขียน, kernel สำหรับตรวจสิทธิ์และรันงาน, และ Jev สำหรับการตัดสินใจแบบมีชนิดข้อมูล เช่น ระดับ context ที่ควรส่งให้ query หนึ่ง ๆ Jev ใช้ TypeSafe API ภายนอก; ค่าเริ่มต้นของ schema-v3 ใช้ตัวเลือกแบบ local และไม่ส่ง source ออกไป

## เริ่ม schema-v3

หลัง `harness init` ให้คัดลอก contract ตัวเลือกมาแก้:

```powershell
Copy-Item .harness/runtime/assets/templates/RUN-CONTRACT-JEV.json .harness/RUN-CONTRACT.json
```

ตั้งค่า `project_id`, `run_id`, `task`, verifier และ model profile ให้ตรงโปรเจกต์ แล้วตรวจและเริ่ม run:

```powershell
harness run-validate --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
harness run --project . --contract .harness/RUN-CONTRACT.json --adapter-argv-file .harness/ADAPTER-ARGV.json --json
```

contract นี้เปิด query-time context assembly โดยใช้ local extractive selector ไม่ต้องใช้ API key และไม่เปลี่ยนพฤติกรรม schema-v1/v2

ถ้าต้องการให้ Jev ตัดสินใจจากข้อมูล public ให้ตั้ง `turn_policy.decision_provider` เป็น `jev-public`, เพิ่ม path patterns ที่ผู้ดูแลยืนยันว่า public ใน `sensitivity`, ตั้งราคา input/output ที่ตรวจสอบแล้ว และให้ `TYPESAFE_API_KEY` อยู่ใน environment ของ kernel เท่านั้น Jev จะได้รับ query และ chunks ที่เลือก ห้ามตั้ง public ให้ source, logs หรือ task ที่เป็นความลับ

สำหรับ context snapshot แบบ standalone ให้ใช้ `harness turn-build` โดยปกติจะเลือกในเครื่อง หากใช้ `--jev-public` ต้องกำหนด policy file ด้วย `--policy`; ตัวโปรแกรมจะปฏิเสธ chunk ที่ไม่มี path rule ระบุเป็น public ส่วน query ต้องเป็น public ด้วย คำสั่งนี้เป็นการส่งข้อมูลภายนอกอย่างชัดเจน ตัวอย่าง policy ต้องระบุ rule เช่น `{"glob":"docs/*","tier":"public"}` เฉพาะเมื่อไฟล์ใน path นั้นเปิดเผยได้จริง

## แนวคิด 10 ข้อและสถานะจริง

| แนวคิด | สถานะใน Harness |
| --- | --- |
| แยก LLM / Harness / Jev | มี: LLM เขียน, kernel ตรวจและรัน, Jev ให้คำตัดสินแบบ typed |
| ประกอบ context ตาม query | มีใน schema-v3; evidence เต็มยังอยู่ใน ledger |
| คิดต้นทุนรวมการส่ง context กลับ | มี `harness route-cost`; เป็นประมาณการจากราคาและ token counts ที่ผู้ใช้ป้อน ไม่มี auto model switch |
| วัด retrieval และ token | มี provider usage counters และ context byte attribution; bytes ไม่ใช่ billed tokens |
| hide / short / long / full | มี; selector ในเครื่องเป็น extractive, Jev ตัดสินได้เฉพาะเมื่อส่งข้อมูล public |
| เปิดเผย tool schema เป็นชั้น | มี catalog และ `tools-disclose`; kernel tool set ยังมีจำนวนจำกัด |
| โหลด instructions ตามเงื่อนไข | มีใน schema-v3; instructions ที่ใช้งานถูก pin ใน context |
| route ตาม trust | มี path sensitivity floors แต่ model profile mapping เป็น policy assertion ไม่ใช่ endpoint attestation |
| shared retrieval | มี observer packet/callback แบบ read-only; ยังไม่ใช่ background service |
| ตรวจ command ก่อนรัน | มี allow/ask/deny และ script digest; ยังต้องใช้ OS sandbox ป้องกัน filesystem/network access |

## ต้นทุนและข้อจำกัด

การแก้ล่าสุดตัดผลลัพธ์ tool ชุดล่าสุดที่เคยซ้ำทั้งใน `tool_results` และ `turn_context` บน fixture สังเคราะห์ 8 ผลลัพธ์ request ลดจาก 124,040 เหลือ 104,898 bytes (15.4%) นี่เป็นการวัดขนาด serialized request ไม่ใช่ billed-token saving หรือผล benchmark ของ task quality

Unreal Labs รายงาน savings สูงสุด 40% จาก benchmark ของผู้พัฒนาเอง งานนั้นไม่ใช่ผล Harness บทความอธิบาย async operations และ prompt/result overhead; สำหรับ Harness ยังไม่มี benchmark ที่ยืนยันว่า operation manager แบบ async ลดค่า model ได้ ดู [Async Operation Runtime](../skills/best-in-code/references/async-operation-runtime.md) ก่อนนำแนวคิดนี้ไปทำ runtime change

Harness ไม่ได้รวม Exa, Gemini API adapter, local/edge Jev, Cua หรือ `tools/jev-assistant.mjs` การเขียนค่า `READY` ใน `CONFIG.md` อย่างเดียวไม่ได้เปิด integration เหล่านั้น

## เอกสารอ้างอิง

- [Jev runtime guide](../skills/best-in-code/references/jev-runtime.md)
- [Async operation runtime](../skills/best-in-code/references/async-operation-runtime.md)
- [Unreal Agent research](https://unreallabs.ai/blog/unreal-agent/) และ [source at reviewed commit](https://github.com/unreallabsai/unreal-agent/tree/b7c9bf1c5c2fa4127255c07727a7c8413e23944a)
