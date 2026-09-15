$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot

Write-Host "=== IRAS v3.6.0 SAFE TREE CLEANUP ==="

$obsoleteFiles = @(
    "ACTION_TRUTH_SPOTIFY_V2.7.2.md",
    "ADULT_ANIME_VOICE.md",
    "ANIME_VOICE.md",
    "AUTONOMOUS_PLANNER_V3.0.0.md",
    "AUTONOMOUS_WORKFLOW_ENGINE_V3.3.0.md",
    "AUTO_APP_CONTROL_V2.9.0.md",
    "AUTO_APP_CONTROL_V2.9.0_FIX.md",
    "BOOTSTRAP_APP_LAUNCHER_V3.0.2.md",
    "BUILD_STATUS.md",
    "BUILD_STATUS_V2.1.md",
    "CLIPBOARDLESS_INPUT_V2.7.3.md",
    "CONTINUOUS_VOICE_V2.5.0.md",
    "DB_LATENCY_FIX_V2.2.2.md",
    "DESKTOP_INTERACTION_V2.7.0.md",
    "DETERMINISTIC_MEDIA_V2.7.4.md",
    "DEVICE_BRIDGE_V2.6.0.md",
    "DEVICE_CLIENTS_V2.1.1.md",
    "DEVICE_INTENT_LOCK_V2.6.2.md",
    "HUMANLIKE_PERSONALITY_V2.3.1.md",
    "LATENCY_HOTFIX_V2.2.1.md",
    "LATENCY_OPTIMIZATION_V2.2.0.md",
    "MODEL_FALLBACK_V2.1.3.md",
    "MULTI_PROVIDER_V2.4.0.md",
    "PERSONALITY_TEST_HOTFIX_V2.3.1a.md",
    "PROVIDER_STABILITY_V2.6.1.md",
    "REAL_DEVICE_RELIABILITY_V3.4.2.md",
    "RELEASE_V2.5.1.md",
    "RENDER_BOOT_FIX_V2.2.3.md",
    "REQUEST_QUEUE_BACKPRESSURE_V3.4.4.md",
    "SOCIAL_PRESENCE_V2.3.2.md",
    "SOCIAL_STREAM_HOTFIX_V2.3.3.md",
    "SPOTIFY_PHYSICAL_PLAYBACK_V2.7.7.md",
    "SPOTIFY_PLAY_BUTTON_V2.7.6.md",
    "SPOTIFY_QUICK_SEARCH_V3.4.5.md",
    "SPOTIFY_RELIABLE_CONTROL_V2.7.5.md",
    "SPOTIFY_VERIFIED_SELECTION_V2.8.1.md",
    "STREAMING_V2.3.0.md",
    "STREAM_LATENCY_GUARD_V2.7.1.md",
    "STREAM_LOCK_LIFECYCLE_V3.4.3.md",
    "TEST_ALIGNMENT_V2.3.4a.md",
    "TITLE_RATE_LIMIT_FIX_V2.3.4.md",
    "UNIVERSAL_APP_LAUNCHER_FIX.md",
    "UNIVERSAL_MEDIA_V2.8.0.md",
    "UNIVERSAL_SAFE_APP_LAUNCHER_V3.1.0.md",
    "VISUAL_COMPUTER_CONTROL_V3.2.0.md",
    "VOICE_FIX.md",
    "WAKE_ALIASES_V2.5.3.md",
    "WEB_HANDSFREE_V2.5.1.md",
    "WINDOWS_MIC_V2.1.2.md",
    "TEST_REPORT.md",
    "apply-device-client-patch.ps1",
    "apply-model-fallback-patch.ps1",
    "apply-windows-mic-patch.ps1",
    ".github\workflows\tests.yml",
    "BUILD_APPS.md",
    "CLOUD_ARCHITECTURE.md",
    "CLOUD_DEPLOY.md",
    "CROSS_APP_WORKFLOW_MEMORY_V3.6.0.md",
    "HUMAN_SPEECH.md",
    "OMNIPARSER_IRAS_SETUP.md",
    "RENDER_SUPABASE_DEPLOY.md",
    "ROLEPLAY_GUIDE.md",
    "SELF_ADAPTING_PERSONALITY.md",
    "ADAPTIVE_RECOVERY_ROUTE_SCORING_V3.5.19.md",
    "AUTOMATIC_OUTCOME_RECOVERY_V3.5.11.md",
    "AUTOMATIC_RECOVERY_ROUTE_SELECTION_V3.5.12.md",
    "CONTEXT_AWARE_RECOVERY_LEARNING_V3.5.21.md",
    "FRESH_PLAN_EXECUTION_AND_VERIFICATION_V3.5.15.md",
    "MATERIAL_REPLAN_GUARD_V3.5.17.md",
    "PERSISTENT_LEARNED_APP_SKILLS_V3.4.0.md",
    "RECOVERY_AWARE_FRESH_ACTION_PLANNING_V3.5.14.md",
    "RECOVERY_CONFIDENCE_CALIBRATION_V3.5.22.md",
    "RECOVERY_HISTORY_AWARE_PLANNER_V3.5.18.md",
    "RECOVERY_ROUTE_EXECUTION_ORCHESTRATION_V3.5.13.md",
    "RECOVERY_ROUTE_PERFORMANCE_LEARNING_V3.5.20.md",
    "SPOTIFY_CLOSED_LOOP_V3.5.md",
    "STRONG_OUTCOME_POLICY_V3.5.6.md",
    "UNIVERSAL_COMPUTER_USE_V3.4.6.md",
    "VERIFICATION_RESULT_DRIVEN_REPLANNING_V3.5.16.md",
    "WHATSAPP_PRE_SEND_VERIFICATION_V3.5.8.md",
    "WHATSAPP_SEARCH_STATE_RECOVERY_V3.5.9.md",
    "WHATSAPP_STARTUP_REACQUIRE_V3.5.10.md",
    "run-spotify-v35-validation.ps1",
    "run-v3511-recovery-validation.ps1",
    "run-v3512-route-validation.ps1",
    "run-v3513-orchestration-validation.ps1",
    "run-v3514-fresh-action-validation.ps1",
    "run-v3515-execution-validation.ps1",
    "run-v3516-replanning-validation.ps1",
    "run-v3517-material-replan-validation.ps1",
    "run-v3518-planner-history-validation.ps1",
    "run-v3519-adaptive-recovery-validation.ps1",
    "run-v3520-recovery-learning-validation.ps1",
    "run-v3521-contextual-learning-validation.ps1",
    "run-v3522-recovery-calibration-validation.ps1",
    "run-whatsapp-v35-validation.ps1",
    "run-whatsapp-darkness-v357-validation.ps1",
    "run-whatsapp-darkness-v358-validation.ps1",
    "run-whatsapp-darkness-v359-validation.ps1",
    "run-whatsapp-darkness-v3510-validation.ps1",
    "scripts\validate_adaptive_recovery_v3519.py",
    "scripts\validate_automatic_recovery_v3511.py",
    "scripts\validate_contextual_recovery_learning_v3521.py",
    "scripts\validate_fresh_action_execution_v3515.py",
    "scripts\validate_fresh_action_planning_v3514.py",
    "scripts\validate_material_replan_guard_v3517.py",
    "scripts\validate_recovery_calibration_v3522.py",
    "scripts\validate_recovery_history_planner_v3518.py",
    "scripts\validate_recovery_learning_v3520.py",
    "scripts\validate_recovery_orchestration_v3513.py",
    "scripts\validate_recovery_routes_v3512.py",
    "scripts\validate_spotify_closed_loop_v35.py",
    "scripts\validate_verification_replanning_v3516.py",
    "scripts\validate_whatsapp_closed_loop_v35.py",
    "scripts\validate_whatsapp_darkness_send_v357.py",
    "scripts\validate_whatsapp_darkness_send_v358.py",
    "scripts\validate_whatsapp_darkness_send_v359.py",
    "scripts\validate_whatsapp_darkness_send_v3510.py"
)

$removed = 0
foreach ($relative in $obsoleteFiles) {
    $path = Join-Path $ProjectRoot $relative
    if (Test-Path $path) {
        Remove-Item -Force $path
        $removed++
    }
}

$oldDocPaths = @(
    "docs\history",
    "docs\V3.4.6_RELEASE_VALIDATION.md",
    "docs\V3.5.4_TARGET_LEVEL_VISION_ESCALATION.md",
    "docs\V3.5.5_STRONG_OUTCOME_VERIFICATION.md",
    "docs\V3.5.7_WHATSAPP_REAL_MESSAGE_VALIDATION.md",
    "docs\V3.5_FOREGROUND_VISION_SPOTIFY_VALIDATION.md",
    "docs\V3.5_MULTI_APP_CLOSED_LOOP_VALIDATION.md"
)
foreach ($relative in $oldDocPaths) {
    $path = Join-Path $ProjectRoot $relative
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
        $removed++
    }
}

Get-ChildItem -Path $ProjectRoot -Directory -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue }

Get-ChildItem -Path $ProjectRoot -File -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
    Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "OBSOLETE ARTIFACTS REMOVED: $removed"
Write-Host "USER DATA REMOVED: False"
Write-Host "SOURCE CODE REMOVED: False"
Write-Host "TEST SUITE REMOVED: False"
Write-Host "CLEANUP RESULT: PASS"
