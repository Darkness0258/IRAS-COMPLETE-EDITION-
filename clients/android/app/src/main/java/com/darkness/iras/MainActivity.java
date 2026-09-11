package com.darkness.iras;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.media.MediaPlayer;
import android.os.*;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.text.InputType;
import android.view.*;
import android.widget.*;

import org.json.JSONObject;

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

    private LinearLayout chat;
    private EditText input;
    private TextView status;
    private Button handsButton;

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

    private long conversationUntil = 0L;
    private String lastSpokenText = "";

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

    private TextView tv(
        String text,
        int size
    ) {
        TextView v =
            new TextView(this);

        v.setText(text);
        v.setTextColor(Color.WHITE);
        v.setTextSize(size);
        v.setPadding(
            16,
            12,
            16,
            12
        );

        return v;
    }

    private void buildUi() {
        LinearLayout root =
            new LinearLayout(this);

        root.setOrientation(
            LinearLayout.VERTICAL
        );
        root.setPadding(
            12,
            12,
            12,
            12
        );
        root.setBackgroundColor(
            Color.rgb(
                11,
                13,
                18
            )
        );

        LinearLayout top =
            new LinearLayout(this);

        top.setGravity(
            Gravity.CENTER_VERTICAL
        );

        TextView title =
            tv(
                "IRAS",
                22
            );

        top.addView(
            title,
            new LinearLayout.LayoutParams(
                0,
                -2,
                1
            )
        );

        Button settings =
            new Button(this);

        settings.setText("Server");
        settings.setOnClickListener(
            v -> showSettings()
        );

        top.addView(settings);
        root.addView(top);

        ScrollView scroll =
            new ScrollView(this);

        chat =
            new LinearLayout(this);

        chat.setOrientation(
            LinearLayout.VERTICAL
        );

        scroll.addView(chat);

        root.addView(
            scroll,
            new LinearLayout.LayoutParams(
                -1,
                0,
                1
            )
        );

        LinearLayout row =
            new LinearLayout(this);

        handsButton =
            new Button(this);

        handsButton.setOnClickListener(
            v -> toggleHandsFree()
        );
        row.addView(handsButton);

        Button mic =
            new Button(this);

        mic.setText("Mic");
        mic.setOnClickListener(
            v -> listenOnce()
        );
        row.addView(mic);

        input =
            new EditText(this);

        input.setTextColor(
            Color.WHITE
        );
        input.setHintTextColor(
            Color.GRAY
        );
        input.setHint(
            "Talk to IRAS..."
        );
        input.setSingleLine(true);
        input.setOnEditorActionListener(
            (v, actionId, event) -> {
                send();
                return true;
            }
        );

        row.addView(
            input,
            new LinearLayout.LayoutParams(
                0,
                -2,
                1
            )
        );

        Button send =
            new Button(this);

        send.setText("Send");
        send.setOnClickListener(
            v -> send()
        );
        row.addView(send);

        root.addView(row);

        status =
            tv(
                "Ready · continuous voice",
                12
            );

        status.setTextColor(
            Color.GRAY
        );

        root.addView(status);

        setContentView(root);
    }

    private TextView addMessageView(
        String who,
        String text
    ) {
        TextView v =
            tv(
                who + ": " + text,
                16
            );

        v.setBackgroundColor(
            who.equals("You")
                ? Color.rgb(
                    37,
                    42,
                    56
                )
                : Color.rgb(
                    22,
                    26,
                    36
                )
        );

        LinearLayout.LayoutParams p =
            new LinearLayout.LayoutParams(
                -1,
                -2
            );

        p.setMargins(
            0,
            6,
            0,
            6
        );

        chat.addView(
            v,
            p
        );

        return v;
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

        box.addView(server);
        box.addView(token);
        box.addView(wake);

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
                generation
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
        int generation
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
            "en-US"
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

    private WakeResult extractWakeCommand(
        String text
    ) {
        String raw =
            text.trim();

        Pattern p =
            Pattern.compile(
                "\\b(?:(?:hey|okay|ok)\\s+)?"
                + Pattern.quote(
                    wakeWord()
                )
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

        if (
            h.size()
            == 1
            && h.contains(
                wakeWord()
                    .toLowerCase(
                        Locale.US
                    )
            )
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
    }

    @Override protected void onPause() {
        appForeground =
            false;

        stopRecognition();
        super.onPause();
    }

    @Override protected void onDestroy() {
        appForeground =
            false;

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
