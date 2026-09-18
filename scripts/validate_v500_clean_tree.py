from __future__ import annotations
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REQUIRED=[
 'README.md','ARCHITECTURE.md','RC3-FEATURE-MATRIX.md','RELEASE-MANIFEST.json',
 'docs/V5_0_RC3_NOTES.md','tests/test_v500_capability_layer.py','tests/test_v500_rc3_complete_operating_layer.py',
 'tests/test_v500_rc3_all_features.py','tests/test_v500_rc3_managed_vision.py',
 'scripts/validate_v500_integrated.py','scripts/validate_v500_clean_tree.py','scripts/package_v500_rc3.py','run-v500-validation.ps1',
 'install.ps1','run-iras.ps1','setup-omniparser.ps1',
 'src/iras/v5/runtime.py','src/iras/v5/scheduler.py','src/iras/v5/monitoring.py','src/iras/v5/semantic_memory.py','src/iras/v5/knowledge_graph.py',
 'src/iras/v5/coding_workspace.py','src/iras/v5/capability_learning.py','src/iras/v5/connectors.py','src/iras/v5/connector_adapters.py',
 'src/iras/v5/artifacts.py','src/iras/v5/sandbox.py','src/iras/v5/skills.py','src/iras/v5/encrypted_sync.py','src/iras/v5/goals.py',
 'src/iras/v5/migrations.py','src/iras/v5/home_network.py','src/iras/tools/v5.py','clients/web/index.html',
 'clients/android/app/src/main/java/com/darkness/iras/MainActivity.java','clients/android/app/src/main/AndroidManifest.xml','clients/android/app/build.gradle'
]
SECRET_PATTERNS=[
 re.compile(r'(?i)(?:sk-or-v1|sk-proj|ghp_|github_pat_)[A-Za-z0-9_\-]{12,}'),
 re.compile(r'(?i)OPENROUTER_API_KEY[ \t]*=[ \t]*(?!your_|$)[^\s#]{20,}'),
 re.compile(r'(?i)GROQ_API_KEY[ \t]*=[ \t]*(?!your_|$)[^\s#]{20,}'),
 re.compile(r'(?i)GEMINI_API_KEY[ \t]*=[ \t]*(?!your_|$)[^\s#]{20,}'),
]

def main():
    missing=[x for x in REQUIRED if not (ROOT/x).exists()]
    cache=[];debris=[];secrets=[]
    for p in ROOT.rglob('*'):
        rel=str(p.relative_to(ROOT))
        if {'__pycache__','.pytest_cache','.mypy_cache','.ruff_cache'} & set(p.parts) or p.suffix in {'.pyc','.pyo'}: cache.append(rel)
        if any(part in {'build','dist'} or part.endswith('.egg-info') for part in p.parts): debris.append(rel)
        if p.is_file() and p.name!='.env' and p.suffix.lower() in {'.py','.md','.toml','.yml','.yaml','.ps1','.html','.example'}:
            text=p.read_text(encoding='utf-8',errors='ignore')
            if any(x.search(text) for x in SECRET_PATTERNS): secrets.append(rel)
    print('=== IRAS v5.0 RC3 CLEAN TREE VALIDATION ===')
    print('LOCAL .ENV PRESENT:',(ROOT/'.env').exists())
    print('REQUIRED V5 FILES PRESENT:',not missing)
    print('CACHE/COMPILED DEBRIS PRESENT:',bool(cache))
    print('BUILD/PACKAGING DEBRIS PRESENT:',bool(debris))
    print('OBVIOUS SECRET PATTERNS FOUND:',bool(secrets))
    if missing: print('MISSING:',missing)
    if cache: print('CACHE SAMPLE:',cache[:20])
    if debris: print('DEBRIS SAMPLE:',debris[:20])
    if secrets: print('SECRET SAMPLE:',secrets[:20])
    assert not missing and not cache and not debris and not secrets
    print('RESULT: PASS')

if __name__=='__main__': main()
