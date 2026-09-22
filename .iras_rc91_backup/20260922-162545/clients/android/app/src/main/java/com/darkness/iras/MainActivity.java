package com.darkness.iras;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.media.MediaPlayer;
import android.os.*;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.text.InputType;
import android.view.*;
import android.view.animation.DecelerateInterpolator;
import android.widget.*;

import org.json.JSONObject;
import org.json.JSONArray;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.*;

public class MainActivity extends Activity {
    private static final String DEFAULT_SERVER =
        "https://iras-cloud.onrender.com";
    private static final int MIC_PERMISSION = 7;
    private static final int NOTIFICATION_PERMISSION = 8;
    private static final String COMPANION_CHANNEL = "iras_companion";

    private LinearLayout chat;
    private ScrollView chatScroll;
    private EditText input;
    private TextView status;
    private Button handsButton;
    private Button masterButton;

    private SpeechRecognizer recognizer;
    private android.content.SharedPreferences prefs;
    private MediaPlayer player;
    private File voiceFile;

    private final Handler mainHandler =
        new Handler(Looper.getMainLooper());
    private final AtomicInteger requestGeneration =
        new AtomicInteger(0);

    private volatile HttpURLConnection activeChatConnection;
    private volatile boolean requestActive = false;
    private volatile boolean handsFree = false;
    private volatile boolean recognitionRunning = false;
    private volatile boolean appForeground = true;
    private volatile boolean companionPolling = false;
    private volatile boolean cloudSyncing = false;
    private volatile boolean cloudHistoryLoaded = false;
    private final Set<String> activeApprovalIds =
        Collections.synchronizedSet(new HashSet<>());
    private final Set<String> cloudRenderedMessageIds =
        Collections.synchronizedSet(new HashSet<>());
    private final Runnable companionPollRunnable =
        this::pollCompanionAsync;

    private long conversationUntil = 0L;
    private String lastSpokenText = "";
    private volatile String masterRemoteSessionId = "";
    private volatile String masterRemoteSessionToken = "";
    private volatile long masterRemoteExpiresAt = 0L;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);

        prefs = getSharedPreferences(
            "iras",
            MODE_PRIVATE
        );

        handsFree = prefs.getBoolean(
            "hands_free",
            true
        );

        buildUi();

        if (
            prefs.getString(
                "token",
                ""
            ).isEmpty()
        ) {
            showSettings();
        }

        updateHandsButton();
        updateMasterButton();
        createCompanionNotificationChannel();
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_PERMISSION);
        }
        syncCloudSessionAsync(true);
        mainHandler.postDelayed(companionPollRunnable, 900);

        if (
            handsFree
            && checkSelfPermission(
                Manifest.permission.RECORD_AUDIO
            ) == PackageManager.PERMISSION_GRANTED
        ) {
            mainHandler.postDelayed(
                this::startHandsFreeListening,
                700
            );
        }
    }

    private String serverUrl() {
        String value =
            prefs.getString(
                "server",
                DEFAULT_SERVER
            ).trim();

        return value.isEmpty()
            ? DEFAULT_SERVER
            : value.replaceAll("/$", "");
    }

    private String wakeWord() {
        String value =
            prefs.getString(
                "wake_word",
                "IRAS"
            ).trim();

        return value.isEmpty()
            ? "IRAS"
            : value;
    }

    private String speechLanguage() {
        String configured = prefs.getString("speech_language", "auto").trim();
        if (configured.isEmpty() || configured.equalsIgnoreCase("auto")) {
            String system = Locale.getDefault().toLanguageTag();
            return system == null || system.trim().isEmpty() ? "en-US" : system;
        }
        return configured;
    }

    private int dp(float value) {
        return Math.round(
            value * getResources().getDisplayMetrics().density
        );
    }

    private GradientDrawable rounded(
        int color,
        float radiusDp,
        int strokeColor
    ) {
        GradientDrawable drawable =
            new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        if (strokeColor != Color.TRANSPARENT) {
            drawable.setStroke(dp(1), strokeColor);
        }
        return drawable;
    }

    private GradientDrawable gradient(
        int start,
        int end,
        float radiusDp
    ) {
        GradientDrawable drawable =
            new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{start, end}
            );
        drawable.setCornerRadius(dp(radiusDp));
        return drawable;
    }

    private TextView tv(
        String text,
        int size
    ) {
        TextView v =
            new TextView(this);

        v.setText(text);
        v.setTextColor(Color.rgb(241, 245, 255));
        v.setTextSize(size);
        v.setLineSpacing(0f, 1.06f);
        v.setPadding(
            dp(14),
            dp(10),
            dp(14),
            dp(10)
        );

        return v;
    }

    private void styleButton(
        Button button,
        boolean primary
    ) {
        button.setAllCaps(false);
        button.setTextSize(13);
        button.setMinHeight(0);
        button.setMinWidth(0);
        button.setPadding(
            dp(14),
            dp(10),
            dp(14),
            dp(10)
        );
        button.setTextColor(
            primary
                ? Color.rgb(7, 14, 26)
                : Color.rgb(218, 225, 240)
        );
        button.setBackground(
            primary
                ? gradient(
                    Color.rgb(166, 180, 255),
                    Color.rgb(102, 224, 255),
                    14
                )
                : rounded(
                    Color.rgb(18, 25, 39),
                    14,
                    Color.rgb(45, 56, 78)
                )
        );
        if (Build.VERSION.SDK_INT >= 21) {
            button.setElevation(dp(primary ? 5 : 1));
            button.setStateListAnimator(null);
        }
        button.setOnTouchListener(
            (v, event) -> {
                if (event.getAction() == MotionEvent.ACTION_DOWN) {
                    v.animate()
                        .scaleX(0.97f)
                        .scaleY(0.97f)
                        .setDuration(90)
                        .start();
                } else if (
                    event.getAction() == MotionEvent.ACTION_UP
                    || event.getAction() == MotionEvent.ACTION_CANCEL
                ) {
                    v.animate()
                        .scaleX(1f)
                        .scaleY(1f)
                        .setDuration(150)
                        .setInterpolator(new DecelerateInterpolator())
                        .start();
                }
                return false;
            }
        );
    }

    private void animateIn(
        View view,
        long delay
    ) {
        view.setAlpha(0f);
        view.setTranslationY(dp(8));
        view.animate()
            .alpha(1f)
            .translationY(0f)
            .setStartDelay(delay)
            .setDuration(240)
            .setInterpolator(new DecelerateInterpolator())
            .start();
    }

    private void buildUi() {
        getWindow().setStatusBarColor(Color.rgb(7, 10, 17));
        getWindow().setNavigationBarColor(Color.rgb(7, 10, 17));

        LinearLayout root =
            new LinearLayout(this);

        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(
            dp(14),
            dp(10),
            dp(14),
            dp(10)
        );
        root.setBackground(
            gradient(
                Color.rgb(7, 10, 17),
                Color.rgb(10, 14, 24),
                0
            )
        );
        root.setOnApplyWindowInsetsListener(
            (view, insets) -> {
                view.setPadding(
                    dp(14) + insets.getSystemWindowInsetLeft(),
                    dp(10) + insets.getSystemWindowInsetTop(),
                    dp(14) + insets.getSystemWindowInsetRight(),
                    dp(10) + insets.getSystemWindowInsetBottom()
                );
                return insets;
            }
        );

        LinearLayout top =
            new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setPadding(
            dp(4),
            dp(5),
            dp(4),
            dp(12)
        );

        ImageView orb = new ImageView(this);
        orb.setImageResource(R.drawable.iras_logo);
        orb.setScaleType(ImageView.ScaleType.CENTER_CROP);
        orb.setContentDescription("IRAS logo");
        orb.setBackground(
            rounded(
                Color.rgb(20, 28, 46),
                15,
                Color.rgb(48, 62, 94)
            )
        );
        orb.setClipToOutline(true);
        LinearLayout.LayoutParams orbParams =
            new LinearLayout.LayoutParams(
                dp(52),
                dp(52)
            );
        orbParams.setMargins(0, 0, dp(10), 0);
        top.addView(orb, orbParams);

        LinearLayout titleStack =
            new LinearLayout(this);
        titleStack.setOrientation(LinearLayout.VERTICAL);

        TextView title =
            tv("IRAS", 21);
        title.setPadding(0, 0, 0, 0);
        title.setLetterSpacing(0.08f);
        title.setTypeface(null, android.graphics.Typeface.BOLD);

        TextView subtitle =
            tv("Unified intelligence workspace", 11);
        subtitle.setPadding(0, dp(2), 0, 0);
        subtitle.setTextColor(Color.rgb(130, 143, 169));

        titleStack.addView(title);
        titleStack.addView(subtitle);
        top.addView(
            titleStack,
            new LinearLayout.LayoutParams(
                0,
                -2,
                1
            )
        );

        Button settings =
            new Button(this);
        settings.setText("Settings");
        settings.setContentDescription("Open IRAS connection settings");
        styleButton(settings, false);
        settings.setOnClickListener(
            v -> showSettings()
        );
        top.addView(settings);

        masterButton = new Button(this);
        masterButton.setText("Master");
        masterButton.setContentDescription("Attach or end IRAS Master Control session");
        styleButton(masterButton, false);
        masterButton.setOnClickListener(v -> toggleMasterSession());
        LinearLayout.LayoutParams masterParams = new LinearLayout.LayoutParams(-2, -2);
        masterParams.setMargins(dp(6), 0, 0, 0);
        top.addView(masterButton, masterParams);
        root.addView(top);

        LinearLayout stateRow =
            new LinearLayout(this);
        stateRow.setGravity(Gravity.CENTER_VERTICAL);
        stateRow.setPadding(
            dp(12),
            dp(8),
            dp(12),
            dp(8)
        );
        stateRow.setBackground(
            rounded(
                Color.rgb(13, 20, 32),
                14,
                Color.rgb(34, 46, 66)
            )
        );
        TextView online =
            tv("●  CLOUD ONLINE", 10);
        online.setPadding(0, 0, 0, 0);
        online.setTextColor(Color.rgb(115, 226, 170));
        stateRow.addView(online);
        TextView sync =
            tv("PC · WEB · MOBILE", 10);
        sync.setGravity(Gravity.END);
        sync.setPadding(0, 0, 0, 0);
        sync.setTextColor(Color.rgb(112, 126, 153));
        stateRow.addView(
            sync,
            new LinearLayout.LayoutParams(
                0,
                -2,
                1
            )
        );
        root.addView(stateRow);

        chatScroll =
            new ScrollView(this);
        chatScroll.setFillViewport(true);
        chatScroll.setClipToPadding(false);
        chatScroll.setPadding(0, dp(8), 0, dp(8));

        chat =
            new LinearLayout(this);
        chat.setOrientation(LinearLayout.VERTICAL);
        chat.setPadding(0, dp(6), 0, dp(8));
        chatScroll.addView(chat);

        root.addView(
            chatScroll,
            new LinearLayout.LayoutParams(
                -1,
                0,
                1
            )
        );

        LinearLayout composer =
            new LinearLayout(this);
        composer.setGravity(Gravity.CENTER_VERTICAL);
        composer.setPadding(
            dp(7),
            dp(7),
            dp(7),
            dp(7)
        );
        composer.setBackground(
            rounded(
                Color.rgb(15, 21, 34),
                19,
                Color.rgb(48, 59, 82)
            )
        );

        handsButton =
            new Button(this);
        handsButton.setContentDescription("Toggle hands-free voice mode");
        styleButton(handsButton, false);
        handsButton.setOnClickListener(
            v -> toggleHandsFree()
        );
        LinearLayout.LayoutParams smallButton =
            new LinearLayout.LayoutParams(
                -2,
                -2
            );
        smallButton.setMargins(0, 0, dp(6), 0);
        composer.addView(handsButton, smallButton);

        Button mic =
            new Button(this);
        mic.setText("Mic");
        mic.setContentDescription("Start one-shot voice input");
        styleButton(mic, false);
        mic.setOnClickListener(
            v -> listenOnce()
        );
        LinearLayout.LayoutParams micParams =
            new LinearLayout.LayoutParams(
                -2,
                -2
            );
        micParams.setMargins(0, 0, dp(7), 0);
        composer.addView(mic, micParams);

        input =
            new EditText(this);
        input.setTextColor(Color.rgb(244, 247, 255));
        input.setHintTextColor(Color.rgb(103, 116, 141));
        input.setHint("Message IRAS…");
        input.setContentDescription("Message IRAS");
        input.setTextSize(15);
        input.setSingleLine(true);
        input.setPadding(dp(12), dp(10), dp(12), dp(10));
        input.setBackgroundColor(Color.TRANSPARENT);
        input.setOnEditorActionListener(
            (v, actionId, event) -> {
                send();
                return true;
            }
        );

        LinearLayout.LayoutParams inputParams =
            new LinearLayout.LayoutParams(
                0,
                -2,
                1
            );
        inputParams.setMargins(0, 0, dp(7), 0);
        composer.addView(input, inputParams);

        Button send =
            new Button(this);
        send.setText("Send");
        send.setContentDescription("Send message to IRAS");
        styleButton(send, true);
        send.setOnClickListener(
            v -> send()
        );
        composer.addView(send);

        root.addView(composer);

        status =
            tv(
                "Ready · continuous voice",
                11
            );
        status.setTextColor(Color.rgb(105, 119, 145));
        status.setPadding(dp(7), dp(7), dp(7), dp(2));
        root.addView(status);

        setContentView(root);
        animateIn(top, 0);
        animateIn(stateRow, 70);
        animateIn(composer, 130);
    }

    private TextView addMessageView(
        String who,
        String text
    ) {
        boolean mine = who.equals("You");

        LinearLayout group =
            new LinearLayout(this);
        group.setOrientation(LinearLayout.VERTICAL);
        group.setGravity(
            mine
                ? Gravity.END
                : Gravity.START
        );

        TextView meta =
            tv(
                mine ? "YOU" : "IRAS",
                9
            );
        meta.setPadding(dp(7), 0, dp(7), dp(4));
        meta.setTextColor(
            mine
                ? Color.rgb(143, 157, 196)
                : Color.rgb(151, 173, 255)
        );
        meta.setLetterSpacing(0.10f);
        group.addView(meta);

        TextView bubble =
            tv(text, 15);
        bubble.setMaxWidth(dp(340));
        bubble.setTextIsSelectable(true);
        bubble.setBackground(
            mine
                ? gradient(
                    Color.rgb(39, 48, 82),
                    Color.rgb(29, 38, 65),
                    18
                )
                : rounded(
                    Color.rgb(17, 24, 37),
                    18,
                    Color.rgb(42, 53, 75)
                )
        );
        bubble.setPadding(
            dp(15),
            dp(12),
            dp(15),
            dp(12)
        );
        group.addView(bubble);

        LinearLayout.LayoutParams params =
            new LinearLayout.LayoutParams(
                -1,
                -2
            );
        params.setMargins(
            0,
            dp(8),
            0,
            dp(8)
        );

        chat.addView(group, params);
        animateIn(group, 0);
        chatScroll.post(
            () -> chatScroll.smoothScrollTo(
                0,
                chat.getBottom()
            )
        );

        return bubble;
    }

    private void appendStream(
        TextView view,
        String text
    ) {
        runOnUiThread(
            () -> view.append(text)
        );
    }

    private void showSettings() {
        LinearLayout box =
            new LinearLayout(this);

        box.setOrientation(
            LinearLayout.VERTICAL
        );
        box.setPadding(
            30,
            10,
            30,
            0
        );

        EditText server =
            new EditText(this);

        server.setHint(
            DEFAULT_SERVER
        );
        server.setText(
            serverUrl()
        );

        EditText token =
            new EditText(this);

        token.setHint(
            "IRAS access token"
        );
        token.setText(
            prefs.getString(
                "token",
                ""
            )
        );
        token.setInputType(
            InputType.TYPE_CLASS_TEXT
            | InputType.TYPE_TEXT_VARIATION_PASSWORD
        );

        EditText wake =
            new EditText(this);

        wake.setHint("IRAS");
        wake.setText(
            wakeWord()
        );

        EditText language = new EditText(this);
        language.setHint("Speech language: auto, ur-PK, en-US, hi-IN...");
        language.setText(prefs.getString("speech_language", "auto"));

        EditText voiceMood = new EditText(this);
        voiceMood.setHint("Voice mood: calm / warm / bright / neutral");
        voiceMood.setText(prefs.getString("voice_mood", "calm"));

        EditText voiceGender = new EditText(this);
        voiceGender.setHint("Voice: female / male");
        voiceGender.setText(prefs.getString("voice_gender", "female"));

        box.addView(server);
        box.addView(token);
        box.addView(wake);
        box.addView(language);
        box.addView(voiceMood);
        box.addView(voiceGender);

        new AlertDialog.Builder(this)
            .setTitle(
                "IRAS Server"
            )
            .setView(box)
            .setPositiveButton(
                "Save",
                (d, w) -> {
                    String url =
                        server
                            .getText()
                            .toString()
                            .trim();

                    if (url.isEmpty()) {
                        url =
                            DEFAULT_SERVER;
                    }

                    String wakeValue =
                        wake
                            .getText()
                            .toString()
                            .trim();

                    if (
                        wakeValue
                            .isEmpty()
                    ) {
                        wakeValue =
                            "IRAS";
                    }

                    prefs.edit()
                        .putString(
                            "server",
                            url.replaceAll(
                                "/$",
                                ""
                            )
                        )
                        .putString(
                            "token",
                            token
                                .getText()
                                .toString()
                                .trim()
                        )
                        .putString(
                            "wake_word",
                            wakeValue
                        )
                        .apply();

                    if (handsFree) {
                        startHandsFreeListening();
                    }
                    cloudHistoryLoaded = false;
                    syncCloudSessionAsync(true);
                    mainHandler.removeCallbacks(companionPollRunnable);
                    mainHandler.postDelayed(companionPollRunnable, 250);
                }
            )
            .setNegativeButton(
                "Cancel",
                null
            )
            .show();
    }

    private void updateHandsButton() {
        handsButton.setText(
            handsFree
                ? "Hands-free On"
                : "Hands-free Off"
        );
    }

    private void toggleHandsFree() {
        if (
            !handsFree
            && checkSelfPermission(
                Manifest.permission.RECORD_AUDIO
            )
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                new String[]{
                    Manifest.permission.RECORD_AUDIO
                },
                MIC_PERMISSION
            );
            return;
        }

        handsFree =
            !handsFree;

        prefs.edit()
            .putBoolean(
                "hands_free",
                handsFree
            )
            .apply();

        updateHandsButton();

        if (handsFree) {
            startHandsFreeListening();
        } else {
            stopRecognition();
            status.setText(
                "Hands-free off"
            );
        }
    }

    private void send() {
        String text =
            input
                .getText()
                .toString()
                .trim();

        input.setText("");

        sendText(
            text,
            false
        );
    }

    private void sendText(
        String text,
        boolean interrupt
    ) {
        text =
            text == null
                ? ""
                : text.trim();

        if (text.isEmpty()) {
            return;
        }

        String token =
            prefs.getString(
                "token",
                ""
            );

        if (token.isEmpty()) {
            showSettings();
            return;
        }

        if (
            requestActive
            && !interrupt
        ) {
            return;
        }

        if (interrupt) {
            interruptCurrentTurn();
        }

        final int generation =
            requestGeneration
                .incrementAndGet();

        requestActive = true;

        final String message =
            text;
        final String turnId =
            "turn_" + UUID.randomUUID().toString().replace("-", "");

        addMessageView(
            "You",
            message
        );

        final TextView assistant =
            addMessageView(
                "IRAS",
                ""
            );

        status.setText(
            "IRAS is thinking..."
        );

        new Thread(
            () -> requestStream(
                serverUrl(),
                token,
                message,
                assistant,
                generation,
                turnId
            )
        ).start();
    }

    private void interruptCurrentTurn() {
        requestGeneration
            .incrementAndGet();

        requestActive = false;

        HttpURLConnection c =
            activeChatConnection;

        activeChatConnection =
            null;

        if (c != null) {
            try {
                c.disconnect();
            } catch (
                Exception ignored
            ) {}
        }

        stopVoice();
    }

    private void requestStream(
        String server,
        String token,
        String message,
        TextView assistant,
        int generation,
        String turnId
    ) {
        HttpURLConnection c =
            null;

        StringBuilder reply =
            new StringBuilder();

        try {
            URL u =
                new URL(
                    server
                    + "/v1/chat/stream"
                );

            c =
                (HttpURLConnection)
                    u.openConnection();

            activeChatConnection =
                c;

            c.setRequestMethod(
                "POST"
            );
            c.setConnectTimeout(
                20000
            );
            c.setReadTimeout(
                120000
            );
            c.setDoOutput(
                true
            );

            c.setRequestProperty(
                "Authorization",
                "Bearer " + token
            );
            c.setRequestProperty(
                "Content-Type",
                "application/json"
            );
            c.setRequestProperty(
                "Accept",
                "text/event-stream"
            );
            c.setRequestProperty(
                "X-Device-ID",
                "android"
            );
            if (masterSessionActive()) {
                c.setRequestProperty("X-IRAS-Remote-Session-ID", masterRemoteSessionId);
                c.setRequestProperty("X-IRAS-Remote-Token", masterRemoteSessionToken);
            }

            JSONObject body =
                new JSONObject();

            body.put(
                "message",
                message
            );
            body.put(
                "device_id",
                "android"
            );
            body.put(
                "client_id",
                cloudClientId()
            );
            body.put(
                "thread_id",
                cloudThreadId()
            );
            body.put(
                "turn_id",
                turnId
            );

            try (
                OutputStream os =
                    c.getOutputStream()
            ) {
                os.write(
                    body
                        .toString()
                        .getBytes(
                            StandardCharsets.UTF_8
                        )
                );
            }

            int code =
                c.getResponseCode();

            if (
                code < 200
                || code >= 300
            ) {
                String error =
                    readAll(
                        c.getErrorStream()
                    );

                throw new RuntimeException(
                    "HTTP "
                    + code
                    + ": "
                    + error
                );
            }

            BufferedReader reader =
                new BufferedReader(
                    new InputStreamReader(
                        c.getInputStream(),
                        StandardCharsets.UTF_8
                    )
                );

            String event =
                "message";

            StringBuilder data =
                new StringBuilder();

            String line;

            while (
                (
                    line =
                        reader.readLine()
                )
                != null
            ) {
                if (
                    generation
                    != requestGeneration
                        .get()
                ) {
                    return;
                }

                if (
                    line.isEmpty()
                ) {
                    if (
                        data.length()
                        > 0
                    ) {
                        JSONObject payload =
                            new JSONObject(
                                data.toString()
                            );

                        if (
                            event.equals(
                                "start"
                            )
                        ) {
                            String threadId = payload.optString("thread_id", "").trim();
                            if (!threadId.isEmpty()) {
                                prefs.edit().putString("cloud_thread_id", threadId).apply();
                            }
                            String userMessageId = payload.optString("user_message_id", "").trim();
                            if (!userMessageId.isEmpty()) cloudRenderedMessageIds.add(userMessageId);

                        } else if (
                            event.equals(
                                "token"
                            )
                        ) {
                            String chunk =
                                payload
                                    .optString(
                                        "text",
                                        ""
                                    );

                            if (
                                !chunk.isEmpty()
                            ) {
                                reply.append(
                                    chunk
                                );

                                appendStream(
                                    assistant,
                                    chunk
                                );
                            }

                        } else if (
                            event.equals(
                                "done"
                            )
                        ) {
                            String threadId = payload.optString("thread_id", "").trim();
                            if (!threadId.isEmpty()) {
                                prefs.edit().putString("cloud_thread_id", threadId).apply();
                            }
                            String assistantMessageId = payload.optString("assistant_message_id", "").trim();
                            if (!assistantMessageId.isEmpty()) cloudRenderedMessageIds.add(assistantMessageId);
                            conversationUntil =
                                System
                                    .currentTimeMillis()
                                + 20000L;

                            runOnUiThread(
                                () -> status
                                    .setText(
                                        handsFree
                                            ? "Listening for your next sentence..."
                                            : "Ready"
                                    )
                            );

                        } else if (
                            event.equals(
                                "error"
                            )
                        ) {
                            throw new RuntimeException(
                                payload
                                    .optString(
                                        "message",
                                        "Streaming failed."
                                    )
                            );
                        }
                    }

                    event =
                        "message";

                    data.setLength(
                        0
                    );

                    continue;
                }

                if (
                    line.startsWith(
                        "event:"
                    )
                ) {
                    event =
                        line
                            .substring(6)
                            .trim();

                } else if (
                    line.startsWith(
                        "data:"
                    )
                ) {
                    if (
                        data.length()
                        > 0
                    ) {
                        data.append(
                            '\n'
                        );
                    }

                    data.append(
                        line
                            .substring(5)
                            .trim()
                    );
                }
            }

            requestActive =
                false;

            String finalReply =
                reply
                    .toString()
                    .trim();

            if (
                finalReply.isEmpty()
            ) {
                finalReply =
                    "I lost that response. "
                    + "Try that again.";

                final String fallback =
                    finalReply;

                runOnUiThread(
                    () -> assistant.append(
                        fallback
                    )
                );
            }

            String speakText =
                finalReply;

            requestVoice(
                server,
                token,
                speakText
            );

        } catch (
            Exception e
        ) {
            if (
                generation
                != requestGeneration
                    .get()
            ) {
                return;
            }

            requestActive =
                false;

            runOnUiThread(
                () -> {
                    if (
                        reply.length()
                        == 0
                    ) {
                        assistant.append(
                            "Connection error: "
                            + e.getMessage()
                        );
                    } else {
                        assistant.append(
                            "\n\n[Connection interrupted]"
                        );
                    }

                    status.setText(
                        "AI provider unavailable"
                    );
                }
            );

        } finally {
            if (
                activeChatConnection
                == c
            ) {
                activeChatConnection =
                    null;
            }

            if (c != null) {
                try {
                    c.disconnect();
                } catch (
                    Exception ignored
                ) {}
            }
        }
    }

    private void requestVoice(
        String server,
        String token,
        String text
    ) {
        HttpURLConnection c =
            null;

        try {
            URL u =
                new URL(
                    server
                    + "/v1/tts"
                );

            c =
                (HttpURLConnection)
                    u.openConnection();

            c.setRequestMethod(
                "POST"
            );
            c.setConnectTimeout(
                20000
            );
            c.setReadTimeout(
                120000
            );
            c.setDoOutput(
                true
            );

            c.setRequestProperty(
                "Authorization",
                "Bearer " + token
            );
            c.setRequestProperty(
                "Content-Type",
                "application/json"
            );
            c.setRequestProperty(
                "X-Device-ID",
                "android"
            );

            JSONObject body =
                new JSONObject();

            body.put(
                "text",
                text
            );
            String voiceLanguage = prefs.getString("speech_language", "auto").trim();
            if (!voiceLanguage.isEmpty() && !voiceLanguage.equalsIgnoreCase("auto")) {
                body.put("language", voiceLanguage);
            }
            body.put("mood", prefs.getString("voice_mood", "calm"));
            body.put("voice_gender", prefs.getString("voice_gender", "female"));

            try (
                OutputStream os =
                    c.getOutputStream()
            ) {
                os.write(
                    body
                        .toString()
                        .getBytes(
                            StandardCharsets.UTF_8
                        )
                );
            }

            int code =
                c.getResponseCode();

            if (
                code < 200
                || code >= 300
            ) {
                throw new RuntimeException(
                    "Voice HTTP "
                    + code
                );
            }

            File file =
                File
                    .createTempFile(
                        "iras_voice_",
                        ".mp3",
                        getCacheDir()
                    );

            try (
                InputStream is =
                    c.getInputStream();
                FileOutputStream fos =
                    new FileOutputStream(
                        file
                    )
            ) {
                byte[] buf =
                    new byte[8192];

                int n;

                while (
                    (
                        n =
                            is.read(buf)
                    )
                    != -1
                ) {
                    fos.write(
                        buf,
                        0,
                        n
                    );
                }
            }

            final File ready =
                file;

            runOnUiThread(
                () -> playVoice(
                    ready,
                    text
                )
            );

        } catch (
            Exception e
        ) {
            runOnUiThread(
                () -> status.setText(
                    "Voice unavailable"
                )
            );

        } finally {
            if (c != null) {
                c.disconnect();
            }
        }
    }

    private void playVoice(
        File file,
        String spokenText
    ) {
        stopVoice();

        lastSpokenText =
            spokenText;

        voiceFile =
            file;

        player =
            new MediaPlayer();

        try {
            player.setDataSource(
                file
                    .getAbsolutePath()
            );

            player.setOnPreparedListener(
                mp -> {
                    status.setText(
                        "IRAS is speaking · say "
                        + wakeWord()
                        + " to interrupt"
                    );
                    mp.start();
                }
            );

            player.setOnCompletionListener(
                mp -> {
                    stopVoice();

                    status.setText(
                        handsFree
                            ? "Listening..."
                            : "Ready"
                    );
                }
            );

            player.setOnErrorListener(
                (
                    mp,
                    what,
                    extra
                ) -> {
                    stopVoice();
                    return true;
                }
            );

            player.prepareAsync();

        } catch (
            Exception e
        ) {
            stopVoice();
        }
    }

    private void stopVoice() {
        if (
            player
            != null
        ) {
            try {
                if (
                    player
                        .isPlaying()
                ) {
                    player.stop();
                }
            } catch (
                Exception ignored
            ) {}

            try {
                player.release();
            } catch (
                Exception ignored
            ) {}

            player = null;
        }

        if (
            voiceFile
            != null
        ) {
            try {
                voiceFile.delete();
            } catch (
                Exception ignored
            ) {}

            voiceFile = null;
        }
    }

    private String cloudClientId() {
        String value = prefs.getString("cloud_client_id", "").trim();
        if (value.isEmpty()) {
            value = "android_" + UUID.randomUUID().toString().replace("-", "");
            prefs.edit().putString("cloud_client_id", value).apply();
        }
        return value;
    }

    private String cloudThreadId() {
        return prefs.getString("cloud_thread_id", "").trim();
    }

    private void syncCloudSessionAsync(boolean renderHistory) {
        if (cloudSyncing) return;
        String token = prefs.getString("token", "").trim();
        if (token.isEmpty()) return;
        cloudSyncing = true;
        new Thread(() -> {
            try {
                JSONObject registration = new JSONObject();
                registration.put("client_id", cloudClientId());
                registration.put("name", "IRAS Android - " + Build.MODEL);
                registration.put("platform", "android");
                registration.put("app_version", "5.0.0-rc4");
                JSONArray caps = new JSONArray();
                caps.put("chat");
                caps.put("cloud-sync");
                caps.put("voice");
                caps.put("approvals");
                caps.put("master-session");
                registration.put("capabilities", caps);
                JSONObject registered = companionRequest("POST", "/v1/cloud/clients/register", registration);
                String threadId = cloudThreadId();
                if (threadId.isEmpty()) threadId = registered.optString("active_thread_id", "").trim();
                String sessionPath = "/v1/cloud/session?message_limit=80";
                if (!threadId.isEmpty()) sessionPath += "&thread_id=" + pathPart(threadId);
                JSONObject session = companionRequest("GET", sessionPath, null);
                JSONObject thread = session.optJSONObject("thread");
                if (thread != null) threadId = thread.optString("thread_id", threadId).trim();
                if (threadId.isEmpty()) threadId = session.optString("active_thread_id", "").trim();
                if (!threadId.isEmpty()) prefs.edit().putString("cloud_thread_id", threadId).apply();

                if (renderHistory && !cloudHistoryLoaded) {
                    JSONArray messages = session.optJSONArray("messages");
                    if (messages != null) {
                        ArrayList<JSONObject> copy = new ArrayList<>();
                        for (int i = 0; i < messages.length(); i++) {
                            JSONObject item = messages.optJSONObject(i);
                            if (item != null) copy.add(item);
                        }
                        runOnUiThread(() -> {
                            if (!cloudHistoryLoaded) {
                                for (JSONObject item : copy) {
                                    String role = item.optString("role", "");
                                    String content = item.optString("content", "");
                                    String messageId = item.optString("message_id", "").trim();
                                    if (!messageId.isEmpty()) cloudRenderedMessageIds.add(messageId);
                                    if (content.isEmpty()) continue;
                                    addMessageView("user".equals(role) ? "You" : "IRAS", content);
                                }
                                cloudHistoryLoaded = true;
                                status.setText("Cloud synced");
                            }
                        });
                    }
                }
            } catch (Exception exc) {
                final String detail = exc.getMessage() == null ? exc.getClass().getSimpleName() : exc.getMessage();
                runOnUiThread(() -> status.setText("Cloud sync: " + detail));
            } finally {
                cloudSyncing = false;
            }
        }, "iras-cloud-sync").start();
    }

    private void syncCloudMessagesOnce() throws Exception {
        JSONObject session = companionRequest("GET", "/v1/cloud/session?message_limit=80", null);
        JSONObject thread = session.optJSONObject("thread");
        String activeThread = thread == null ? session.optString("active_thread_id", "").trim() : thread.optString("thread_id", "").trim();
        String currentThread = cloudThreadId();
        JSONArray messages = session.optJSONArray("messages");
        if (messages == null) return;

        ArrayList<JSONObject> fresh = new ArrayList<>();
        boolean switched = !activeThread.isEmpty() && !activeThread.equals(currentThread);
        if (switched) {
            prefs.edit().putString("cloud_thread_id", activeThread).apply();
            cloudRenderedMessageIds.clear();
        }
        for (int i = 0; i < messages.length(); i++) {
            JSONObject item = messages.optJSONObject(i);
            if (item == null) continue;
            String messageId = item.optString("message_id", "").trim();
            if (!messageId.isEmpty() && cloudRenderedMessageIds.contains(messageId)) continue;
            if (!messageId.isEmpty()) cloudRenderedMessageIds.add(messageId);
            fresh.add(item);
        }
        if (fresh.isEmpty() && !switched) return;
        runOnUiThread(() -> {
            if (switched) chat.removeAllViews();
            for (JSONObject item : fresh) {
                String role = item.optString("role", "");
                String content = item.optString("content", "");
                if (content.isEmpty()) continue;
                addMessageView("user".equals(role) ? "You" : "IRAS", content);
            }
            if (!fresh.isEmpty()) status.setText("Cloud synced");
        });
    }

    private void createCompanionNotificationChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(
            COMPANION_CHANNEL,
            "IRAS Companion",
            NotificationManager.IMPORTANCE_DEFAULT
        );
        channel.setDescription("IRAS approvals, monitors and autonomous task notifications");
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) manager.createNotificationChannel(channel);
    }

    private void showCompanionNotification(String title, String body) {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return;
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
            ? new Notification.Builder(this, COMPANION_CHANNEL)
            : new Notification.Builder(this);
        builder.setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title == null || title.isEmpty() ? "IRAS" : title)
            .setContentText(body == null ? "" : body)
            .setAutoCancel(true);
        NotificationManager manager = (NotificationManager)getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager != null) manager.notify((int)(System.currentTimeMillis() & 0x7fffffff), builder.build());
    }

    private void pollCompanionAsync() {
        if (!appForeground || companionPolling) return;
        String token = prefs.getString("token", "").trim();
        if (token.isEmpty()) return;
        companionPolling = true;
        new Thread(() -> {
            try {
                String mobileId = prefs.getString("mobile_id", "").trim();
                if (mobileId.isEmpty()) {
                    JSONObject register = new JSONObject();
                    register.put("name", "IRAS Android - " + Build.MODEL);
                    register.put("platform", "android");
                    JSONObject response = companionRequest("POST", "/v1/v5/mobile/register", register);
                    mobileId = response.optString("mobile_id", "").trim();
                    if (mobileId.isEmpty()) throw new IOException("IRAS mobile registration returned no mobile_id");
                    prefs.edit().putString("mobile_id", mobileId).apply();
                }
                try {
                    companionRequest("POST", "/v1/cloud/clients/" + pathPart(cloudClientId()) + "/heartbeat", new JSONObject());
                    if (!requestActive) syncCloudMessagesOnce();
                } catch (Exception ignored) {}
                JSONObject events = companionRequest("GET", "/v1/v5/mobile/" + pathPart(mobileId) + "/events?limit=50", null);
                processCompanionEvents(mobileId, events.optJSONArray("events"));
            } catch (Exception exc) {
                final String detail = exc.getMessage() == null ? exc.getClass().getSimpleName() : exc.getMessage();
                runOnUiThread(() -> status.setText("Companion: " + detail));
            } finally {
                companionPolling = false;
                if (appForeground) mainHandler.postDelayed(companionPollRunnable, 4000);
            }
        }, "iras-mobile-companion").start();
    }

    private void processCompanionEvents(String mobileId, JSONArray events) {
        if (events == null) return;
        for (int i = 0; i < events.length(); i++) {
            JSONObject event = events.optJSONObject(i);
            if (event == null) continue;
            String eventId = event.optString("event_id", "");
            String kind = event.optString("kind", "");
            JSONObject payload = event.optJSONObject("payload");
            if (payload == null) payload = new JSONObject();
            if ("approval.requested".equals(kind)) {
                String approvalId = payload.optString("approval_id", "");
                if (!approvalId.isEmpty() && activeApprovalIds.add(approvalId)) {
                    JSONObject finalPayload = payload;
                    runOnUiThread(() -> showCompanionApproval(mobileId, eventId, approvalId, finalPayload));
                }
                continue;
            }
            String title = payload.optString("title", "IRAS " + kind);
            String body = payload.optString("body", payload.optString("summary", kind));
            final String message = title + (body.isEmpty() ? "" : "\n" + body);
            runOnUiThread(() -> {
                showCompanionNotification(title, body);
                addMessageView("IRAS", message);
            });
            acknowledgeCompanionEvent(mobileId, eventId);
        }
    }

    private void showCompanionApproval(String mobileId, String eventId, String approvalId, JSONObject eventPayload) {
        JSONObject payload = eventPayload.optJSONObject("payload");
        String kind = eventPayload.optString("kind", "IRAS action");
        String detail = payload == null ? "" : payload.toString();
        AlertDialog dialog = new AlertDialog.Builder(this)
            .setTitle("IRAS approval required")
            .setMessage(kind + (detail.isEmpty() ? "" : "\n\n" + detail))
            .setPositiveButton("Approve", (d, w) -> resolveCompanionApproval(mobileId, eventId, approvalId, true))
            .setNegativeButton("Deny", (d, w) -> resolveCompanionApproval(mobileId, eventId, approvalId, false))
            .create();
        dialog.setCancelable(false);
        dialog.setCanceledOnTouchOutside(false);
        dialog.show();
    }

    private void resolveCompanionApproval(String mobileId, String eventId, String approvalId, boolean approved) {
        new Thread(() -> {
            try {
                JSONObject body = new JSONObject();
                body.put("approved", approved);
                body.put("note", approved ? "Approved from IRAS Android companion" : "Denied from IRAS Android companion");
                companionRequest("POST", "/v1/v5/mobile/approvals/" + pathPart(approvalId), body);
                acknowledgeCompanionEvent(mobileId, eventId);
            } catch (Exception exc) {
                final String detail = exc.getMessage() == null ? exc.getClass().getSimpleName() : exc.getMessage();
                runOnUiThread(() -> status.setText("Approval sync failed: " + detail));
            } finally {
                activeApprovalIds.remove(approvalId);
            }
        }, "iras-mobile-approval").start();
    }

    private void acknowledgeCompanionEvent(String mobileId, String eventId) {
        if (eventId == null || eventId.isEmpty()) return;
        try {
            companionRequest("POST", "/v1/v5/mobile/" + pathPart(mobileId) + "/events/" + pathPart(eventId) + "/ack", new JSONObject());
        } catch (Exception ignored) {}
    }

    private String pathPart(String value) throws UnsupportedEncodingException {
        return URLEncoder.encode(value == null ? "" : value, "UTF-8").replace("+", "%20");
    }

    private boolean masterSessionActive() {
        return !masterRemoteSessionId.isEmpty()
            && !masterRemoteSessionToken.isEmpty()
            && (masterRemoteExpiresAt <= 0L || System.currentTimeMillis() / 1000L < masterRemoteExpiresAt);
    }

    private void updateMasterButton() {
        if (masterButton == null) return;
        boolean active = masterSessionActive();
        masterButton.setText(active ? "MASTER ON" : "Master");
        masterButton.setTextColor(active ? Color.rgb(255, 213, 222) : Color.rgb(218, 225, 240));
        masterButton.setBackground(
            active
                ? rounded(Color.rgb(75, 20, 34), 14, Color.rgb(139, 52, 73))
                : rounded(Color.rgb(18, 25, 39), 14, Color.rgb(45, 56, 78))
        );
    }

    private void toggleMasterSession() {
        if (masterSessionActive()) {
            new AlertDialog.Builder(this)
                .setTitle("End Master session?")
                .setMessage("This ends the Android Master Remote session. It does not turn off the PC's local Master Control.")
                .setPositiveButton("End session", (d, w) -> detachMasterSessionAsync())
                .setNegativeButton("Cancel", null)
                .show();
            return;
        }
        new AlertDialog.Builder(this)
            .setTitle("IRAS Master Control")
            .setMessage(
                "Master Control must already be enabled locally on the Windows PC. "
                + "When attached, this Android chat can carry FULL Remote authority into IRAS.\n\n"
                + "Emergency stop, audit, filesystem roots, Remote authentication and Windows/UAC remain enforced."
            )
            .setPositiveButton("Attach", (d, w) -> attachMasterSessionAsync())
            .setNegativeButton("Cancel", null)
            .show();
    }

    private void attachMasterSessionAsync() {
        status.setText("Checking PC Master Control...");
        new Thread(() -> {
            String createdSessionId = "";
            try {
                JSONObject devicesData = companionRequest("GET", "/v1/devices", null);
                JSONArray devices = devicesData.optJSONArray("devices");
                JSONObject device = null;
                if (devices != null) {
                    for (int i = 0; i < devices.length(); i++) {
                        JSONObject item = devices.optJSONObject(i);
                        if (item == null || !item.optBoolean("online", false)) continue;
                        String platform = item.optString("platform", "").toLowerCase(Locale.ROOT);
                        if (platform.contains("windows")) { device = item; break; }
                        if (device == null) device = item;
                    }
                }
                if (device == null) throw new IOException("No paired Windows PC is online.");

                JSONObject body = new JSONObject();
                body.put("device_id", device.optString("device_id", ""));
                body.put("mode", "full");
                body.put("ttl_seconds", 1800);
                JSONArray scopes = new JSONArray();
                scopes.put("windows");
                scopes.put("master");
                body.put("scopes", scopes);
                JSONObject session = companionRequest("POST", "/v1/remote/sessions", body);
                createdSessionId = session.optString("session_id", "");
                String sessionToken = session.optString("session_token", "");
                long expiresAt = session.optLong("expires_at", 0L);
                if (createdSessionId.isEmpty() || sessionToken.isEmpty()) {
                    throw new IOException("Cloud did not return a usable Master Remote session.");
                }

                JSONObject info = remoteInvoke(createdSessionId, sessionToken, "system_info", new JSONObject(), 30);
                String windowsUser = info.optString("user", "").trim();
                if (windowsUser.isEmpty()) throw new IOException("Could not determine the Windows user for Master Control status.");
                JSONObject readArgs = new JSONObject();
                readArgs.put("path", "C:\\Users\\" + windowsUser + "\\.iras\\master_control.json");
                readArgs.put("max_chars", 12000);
                JSONObject masterFile = remoteInvoke(createdSessionId, sessionToken, "read_text", readArgs, 30);
                String masterText = masterFile.optString("text", masterFile.optString("content", "{}"));
                JSONObject master = masterText.trim().isEmpty() ? new JSONObject() : new JSONObject(masterText);
                boolean masterEnabled = master.optBoolean("enabled", false);
                if (masterEnabled && !master.optBoolean("persistent", false)) {
                    long expiresAtLocal = (long)master.optDouble("expires_at", 0);
                    if (expiresAtLocal > 0 && System.currentTimeMillis() / 1000L >= expiresAtLocal) masterEnabled = false;
                }
                if (!masterEnabled) {
                    try { companionRequest("DELETE", "/v1/remote/sessions/" + pathPart(createdSessionId), null); } catch (Exception ignored) {}
                    throw new IOException("Master Control is OFF on the PC. Run `iras --master-enable 30` locally first.");
                }

                masterRemoteSessionId = createdSessionId;
                masterRemoteSessionToken = sessionToken;
                masterRemoteExpiresAt = expiresAt;
                runOnUiThread(() -> {
                    updateMasterButton();
                    status.setText("MASTER session attached · CRITICAL Remote authority");
                });
            } catch (Exception e) {
                final String detail = e.getMessage();
                runOnUiThread(() -> {
                    updateMasterButton();
                    status.setText("Master unavailable");
                    new AlertDialog.Builder(this)
                        .setTitle("Master Control unavailable")
                        .setMessage(detail + "\n\nEnable locally on the PC with:\niras --master-enable 30")
                        .setPositiveButton("OK", null)
                        .show();
                });
            }
        }, "iras-master-attach").start();
    }

    private void detachMasterSessionAsync() {
        final String sessionId = masterRemoteSessionId;
        masterRemoteSessionId = "";
        masterRemoteSessionToken = "";
        masterRemoteExpiresAt = 0L;
        updateMasterButton();
        status.setText("Android Master session ended");
        if (sessionId.isEmpty()) return;
        new Thread(() -> {
            try { companionRequest("DELETE", "/v1/remote/sessions/" + pathPart(sessionId), null); } catch (Exception ignored) {}
        }, "iras-master-detach").start();
    }

    private JSONObject remoteInvoke(String sessionId, String sessionToken, String action, JSONObject arguments, int timeout) throws Exception {
        HttpURLConnection c = (HttpURLConnection)new URL(serverUrl() + "/v1/remote/invoke").openConnection();
        try {
            c.setRequestMethod("POST");
            c.setConnectTimeout(15000);
            c.setReadTimeout(Math.max(30000, timeout * 1000 + 5000));
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            c.setRequestProperty("Accept", "application/json");
            c.setRequestProperty("X-Device-ID", "android-master");
            c.setRequestProperty("X-IRAS-Remote-Token", sessionToken);
            JSONObject body = new JSONObject();
            body.put("session_id", sessionId);
            body.put("action", action);
            body.put("arguments", arguments == null ? new JSONObject() : arguments);
            body.put("timeout", timeout);
            try (OutputStream os = c.getOutputStream()) {
                os.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
            int code = c.getResponseCode();
            String text = readAll(code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream());
            if (code < 200 || code >= 300) throw new IOException("HTTP " + code + (text.isEmpty() ? "" : ": " + text));
            JSONObject response = text.trim().isEmpty() ? new JSONObject() : new JSONObject(text);
            Object result = response.opt("result");
            return result instanceof JSONObject ? (JSONObject)result : new JSONObject();
        } finally {
            c.disconnect();
        }
    }

    private JSONObject companionRequest(String method, String path, JSONObject body) throws Exception {
        String token = prefs.getString("token", "").trim();
        if (token.isEmpty()) throw new IOException("IRAS token is not configured");
        HttpURLConnection c = (HttpURLConnection)new URL(serverUrl() + path).openConnection();
        try {
            c.setRequestMethod(method);
            c.setConnectTimeout(15000);
            c.setReadTimeout(30000);
            c.setRequestProperty("Authorization", "Bearer " + token);
            c.setRequestProperty("Accept", "application/json");
            c.setRequestProperty("X-Device-ID", "android-companion");
            if (body != null && !"GET".equals(method)) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                try (OutputStream os = c.getOutputStream()) {
                    os.write(body.toString().getBytes(StandardCharsets.UTF_8));
                }
            }
            int code = c.getResponseCode();
            String text = readAll(code >= 200 && code < 300 ? c.getInputStream() : c.getErrorStream());
            if (code < 200 || code >= 300) throw new IOException("HTTP " + code + (text.isEmpty() ? "" : ": " + text));
            return text.trim().isEmpty() ? new JSONObject() : new JSONObject(text);
        } finally {
            c.disconnect();
        }
    }

    private String readAll(
        InputStream is
    ) throws IOException {
        if (
            is
            == null
        ) {
            return "";
        }

        ByteArrayOutputStream b =
            new ByteArrayOutputStream();

        byte[] x =
            new byte[4096];

        int n;

        while (
            (
                n =
                    is.read(x)
            )
            != -1
        ) {
            b.write(
                x,
                0,
                n
            );
        }

        return new String(
            b.toByteArray(),
            StandardCharsets.UTF_8
        );
    }

    private void listenOnce() {
        if (
            checkSelfPermission(
                Manifest.permission.RECORD_AUDIO
            )
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                new String[]{
                    Manifest.permission.RECORD_AUDIO
                },
                MIC_PERMISSION
            );
            return;
        }

        stopVoice();
        startRecognizer(
            false
        );
    }

    private void startHandsFreeListening() {
        if (
            !handsFree
            || !appForeground
        ) {
            return;
        }

        if (
            checkSelfPermission(
                Manifest.permission.RECORD_AUDIO
            )
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                new String[]{
                    Manifest.permission.RECORD_AUDIO
                },
                MIC_PERMISSION
            );
            return;
        }

        startRecognizer(
            true
        );
    }

    private void startRecognizer(
        boolean continuousMode
    ) {
        if (
            recognitionRunning
        ) {
            return;
        }

        if (
            !SpeechRecognizer
                .isRecognitionAvailable(
                    this
                )
        ) {
            status.setText(
                "Speech recognition is unavailable."
            );
            return;
        }

        if (
            recognizer
            == null
        ) {
            recognizer =
                SpeechRecognizer
                    .createSpeechRecognizer(
                        this
                    );
        }

        recognizer
            .setRecognitionListener(
                new android.speech.RecognitionListener() {
                    public void onReadyForSpeech(
                        Bundle b
                    ) {
                        recognitionRunning =
                            true;

                        status.setText(
                            continuousMode
                                ? "Hands-free · say "
                                    + wakeWord()
                                : "Listening..."
                        );
                    }

                    public void onBeginningOfSpeech() {}
                    public void onRmsChanged(float r) {}
                    public void onBufferReceived(byte[] b) {}

                    public void onEndOfSpeech() {
                        if (
                            !continuousMode
                        ) {
                            status.setText(
                                "Thinking..."
                            );
                        }
                    }

                    public void onError(int e) {
                        recognitionRunning =
                            false;

                        if (
                            continuousMode
                            && handsFree
                            && appForeground
                        ) {
                            mainHandler.postDelayed(
                                MainActivity.this
                                    ::startHandsFreeListening,
                                500
                            );
                        } else {
                            status.setText(
                                "Mic error "
                                + e
                            );
                        }
                    }

                    public void onResults(
                        Bundle b
                    ) {
                        recognitionRunning =
                            false;

                        ArrayList<String> results =
                            b.getStringArrayList(
                                SpeechRecognizer
                                    .RESULTS_RECOGNITION
                            );

                        if (
                            results != null
                            && !results.isEmpty()
                        ) {
                            String heard =
                                results.get(0);

                            if (continuousMode) {
                                for (
                                    String candidate :
                                    results
                                ) {
                                    if (
                                        extractWakeCommand(
                                            candidate
                                        ).accepted
                                    ) {
                                        heard =
                                            candidate;
                                        break;
                                    }
                                }

                                handleHandsFreeTranscript(
                                    heard
                                );
                            } else {
                                sendText(
                                    heard,
                                    requestActive
                                );
                            }
                        }

                        if (
                            continuousMode
                            && handsFree
                            && appForeground
                        ) {
                            mainHandler.postDelayed(
                                MainActivity.this
                                    ::startHandsFreeListening,
                                350
                            );
                        }
                    }

                    public void onPartialResults(
                        Bundle b
                    ) {}

                    public void onEvent(
                        int t,
                        Bundle b
                    ) {}
                }
            );

        Intent i =
            new Intent(
                RecognizerIntent
                    .ACTION_RECOGNIZE_SPEECH
            );

        i.putExtra(
            RecognizerIntent
                .EXTRA_LANGUAGE_MODEL,
            RecognizerIntent
                .LANGUAGE_MODEL_FREE_FORM
        );

        i.putExtra(
            RecognizerIntent
                .EXTRA_LANGUAGE,
            speechLanguage()
        );

        i.putExtra(
            RecognizerIntent
                .EXTRA_PARTIAL_RESULTS,
            true
        );

        i.putExtra(
            RecognizerIntent
                .EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS,
            700L
        );

        try {
            recognizer.startListening(
                i
            );
        } catch (
            Exception e
        ) {
            recognitionRunning =
                false;
        }
    }

    private void handleHandsFreeTranscript(
        String heard
    ) {
        if (
            heard == null
            || heard.trim().isEmpty()
        ) {
            return;
        }

        if (
            probableEcho(
                heard,
                lastSpokenText
            )
        ) {
            return;
        }

        WakeResult wake =
            extractWakeCommand(
                heard
            );

        if (
            !wake.accepted
        ) {
            status.setText(
                "Hands-free · say "
                + wakeWord()
            );
            return;
        }

        stopVoice();

        if (
            wake.command
                .isEmpty()
        ) {
            conversationUntil =
                System
                    .currentTimeMillis()
                + 8000L;

            status.setText(
                "Yeah? I'm listening."
            );
            return;
        }

        conversationUntil =
            System
                .currentTimeMillis()
            + 20000L;

        sendText(
            wake.command,
            true
        );
    }

    private static class WakeResult {
        boolean accepted;
        String command;

        WakeResult(
            boolean accepted,
            String command
        ) {
            this.accepted =
                accepted;
            this.command =
                command;
        }
    }

    private List<String> wakeAliases() {
        if (
            !wakeWord()
                .equalsIgnoreCase(
                    "IRAS"
                )
        ) {
            return Collections.singletonList(
                wakeWord()
            );
        }

        return Arrays.asList(
            "IRAS",
            "Iris",
            "Eris",
            "Eras",
            "eye ris",
            "eye-ris",
            "eye ras",
            "eye-rass",
            "Ira's",
            "I R A S",
            "little girl",
            "cute"
        );
    }

    private String wakeAliasRegex(
        String alias
    ) {
        Matcher words =
            Pattern
                .compile(
                    "[a-z0-9']+",
                    Pattern.CASE_INSENSITIVE
                )
                .matcher(alias);

        List<String> parts =
            new ArrayList<>();

        while (
            words.find()
        ) {
            parts.add(
                Pattern.quote(
                    words.group()
                )
            );
        }

        if (
            parts.isEmpty()
        ) {
            return Pattern.quote(
                alias
            );
        }

        return String.join(
            "[\\s-]*",
            parts
        );
    }

    private String wakePattern() {
        List<String> patterns =
            new ArrayList<>();

        for (
            String alias :
            wakeAliases()
        ) {
            patterns.add(
                wakeAliasRegex(
                    alias
                )
            );
        }

        return "(?:"
            + String.join(
                "|",
                patterns
            )
            + ")";
    }

    private WakeResult extractWakeCommand(
        String text
    ) {
        String raw =
            text.trim();

        Pattern p =
            Pattern.compile(
                "^\\s*(?:(?:hey|okay|ok)\\s+)?"
                + wakePattern()
                + "\\b[\\s,.:;!?-]*(.*)$",
                Pattern.CASE_INSENSITIVE
            );

        Matcher m =
            p.matcher(raw);

        if (
            m.find()
        ) {
            return new WakeResult(
                true,
                m.group(1)
                    == null
                    ? ""
                    : m.group(1)
                        .trim()
            );
        }

        if (
            System
                .currentTimeMillis()
            < conversationUntil
        ) {
            return new WakeResult(
                true,
                raw
            );
        }

        return new WakeResult(
            false,
            ""
        );
    }

    private boolean probableEcho(
        String heard,
        String spoken
    ) {
        Set<String> h =
            wordSet(heard);

        Set<String> s =
            wordSet(spoken);

        if (
            h.isEmpty()
            || s.isEmpty()
        ) {
            return false;
        }

        WakeResult wakeOnly =
            extractWakeCommand(
                heard
            );

        if (
            wakeOnly.accepted
            && wakeOnly.command.isEmpty()
        ) {
            return false;
        }

        int overlap =
            0;

        for (
            String word :
            h
        ) {
            if (
                s.contains(
                    word
                )
            ) {
                overlap++;
            }
        }

        double ratio =
            overlap
            / (double)
                Math.max(
                    1,
                    h.size()
                );

        return ratio
            >= 0.68;
    }

    private Set<String> wordSet(
        String text
    ) {
        Set<String> set =
            new HashSet<>();

        Matcher m =
            Pattern
                .compile(
                    "[a-z0-9']+"
                )
                .matcher(
                    text
                        .toLowerCase(
                            Locale.US
                        )
                );

        while (
            m.find()
        ) {
            set.add(
                m.group()
            );
        }

        return set;
    }

    private void stopRecognition() {
        recognitionRunning =
            false;

        if (
            recognizer
            != null
        ) {
            try {
                recognizer.cancel();
            } catch (
                Exception ignored
            ) {}
        }
    }

    @Override public void onRequestPermissionsResult(
        int requestCode,
        String[] permissions,
        int[] grantResults
    ) {
        super.onRequestPermissionsResult(
            requestCode,
            permissions,
            grantResults
        );

        if (
            requestCode
            == MIC_PERMISSION
            && grantResults.length
            > 0
            && grantResults[0]
            == PackageManager
                .PERMISSION_GRANTED
        ) {
            handsFree =
                true;

            prefs.edit()
                .putBoolean(
                    "hands_free",
                    true
                )
                .apply();

            updateHandsButton();
            startHandsFreeListening();
        }
    }

    @Override protected void onResume() {
        super.onResume();
        appForeground =
            true;

        if (
            handsFree
        ) {
            mainHandler.postDelayed(
                this::startHandsFreeListening,
                500
            );
        }
        syncCloudSessionAsync(false);
        mainHandler.removeCallbacks(companionPollRunnable);
        mainHandler.postDelayed(companionPollRunnable, 300);
    }

    @Override protected void onPause() {
        appForeground =
            false;

        mainHandler.removeCallbacks(companionPollRunnable);
        stopRecognition();
        super.onPause();
    }

    @Override protected void onDestroy() {
        appForeground =
            false;

        mainHandler.removeCallbacks(companionPollRunnable);
        stopRecognition();
        stopVoice();

        if (
            recognizer
            != null
        ) {
            recognizer.destroy();
            recognizer = null;
        }

        HttpURLConnection c =
            activeChatConnection;

        if (
            c
            != null
        ) {
            try {
                c.disconnect();
            } catch (
                Exception ignored
            ) {}
        }

        super.onDestroy();
    }
}
