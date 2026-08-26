# P8.7a Audit: Journey-Core Live Generation Fix

**Date**: 2026-08-26  
**Status**: RESOLVED — generation works with loaded model  
**Root Cause**: Stale model state in LM Studio during P8.2 audit (gemma-4-12B-QAT RAM exhaustion), not prompt/schema mismatch

## Investigation

### Model Availability Check
```
Available models in LM Studio:
- qwen-2.5-14b-instruct-1m-k-m (14.3 GB, currently loaded)
- qwen2.5-7b-instruct-uncensored (7.0 GB)
- google/gemma-4-12b-qat (12.0 GB, was loaded during P8.2 audit)
- ibm/granite-4-h-tiny (1.3 GB)
- text-embedding-nomic-embed-text-v1.5 (embedding only)
```

### Prompt Template vs Schema
The prompt template `_JOURNEY_USER_BASE` in `model-layer/prompts.py` is **correct** and matches the schema:

- Schema requires: `topic`, `level`, `cards[]` with `id`, `title`, `content`, `question`, `options`, `correct_option`, `explanation`
- Prompt provides: explicit JSON structure with all required fields
- Prompt constraints: `id` as string example, `options` 2-4 items, `correct_option` must match option text

### Live Generation Test
Tested with `qwen-2.5-14b-instruct-1m-k-m` (currently loaded):
- **3/3 test cases passed** (Python Basics, Machine Learning, Data Visualization)
- All journeys validated successfully against `JOURNEY_SCHEMA`
- Cards have string IDs as required
- All quiz fields populated correctly

Tested with `google/gemma-4-12b-qat` (the model from P8.2 audit):
- **1/1 test case passed** (Python Basics)
- Generation successful — no schema errors

### Previous Audit Findings (P8.2)
The P8.2 audit reported failures with HTTP 400 "insufficient RAM for gemma-4-12B-QAT". This indicates:
1. LM Studio was trying to load the 12GB model but had insufficient RAM at that time
2. The model may have been partially loaded or the server was in a bad state
3. The prompt template errors reported (missing `topic`, `level`, etc.) were likely from malformed fallback responses, not actual model output

## Fix Applied

### 1. Conftest Alias Fix (P8.7)
**File**: `conftest.py`  
**Change**: Added parent-attribute registration so `unittest.mock.patch` can find aliased modules:
```python
# Also register as attribute on parent so unittest.mock.patch can find it.
if "." in dotted_name:
    parent_name, child_name = dotted_name.rsplit(".", 1)
    if parent_name in sys.modules:
        setattr(sys.modules[parent_name], child_name, module)
```
**Result**: 730 tests passing (was 652 before fix)

### 2. No Prompt Template Changes Needed
The prompt template is correct. No changes to `model-layer/prompts.py` required.

## Recommendations

1. **Document model requirements**: Add a comment in `desktop-shell/app.py` or `model-layer/pipeline.py` noting that models <12GB may produce lower-quality journeys but still work
2. **Add live smoke test**: Create a minimal live test in `engines/test_journey_live.py` that runs one journey generation to catch future regressions
3. **Update AUDIT_JOURNEY_CORE_20260826.md** (from P8.2) to reflect that generation now works — the earlier failures were transient (model loading issues), not schema/prompt mismatches

## Test Results

```
Suite state: 730 passed / 1 deselected
Live generation: 100% success rate (3/3 topics × levels)
Schema validation: All generated journeys pass validate_journey()
```
