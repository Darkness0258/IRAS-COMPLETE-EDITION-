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

public class MainActivity extends Activity {
    private static final String DEFAULT_SERVER = "https://iras-cloud.onrender.com";

    private LinearLayout chat;
    private EditText input;
    private TextView status;
    private SpeechRecognizer recognizer;
    private android.content.SharedPreferences prefs;
    private MediaPlayer player;
    private File voiceFile;

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences("iras", MODE_PRIVATE);
        buildUi();

        if (prefs.getString("token", "").isEmpty()) {
            showSettings();
        }
    }

    private String serverUrl() {
        String value = prefs.getString("server", DEFAULT_SERVER).trim();
        return value.isEmpty() ? DEFAULT_SERVER : value.replaceAll("/$", "");
    }

    private TextView tv(String text, int size) {
        TextView v = new TextView(this);
        v.setText(text);
        v.setTextColor(Color.WHITE);
        v.setTextSize(size);
        v.setPadding(16, 12, 16, 12);
        return v;
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(12, 12, 12, 12);
        root.setBackgroundColor(Color.rgb(11, 13, 18));

        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);

        TextView title = tv("IRAS", 22);
        top.addView(title, new LinearLayout.LayoutParams(0, -2, 1));

        Button settings = new Button(this);
        settings.setText("Server");
        settings.setOnClickListener(v -> showSettings());
        top.addView(settings);

        root.addView(top);

        ScrollView scroll = new ScrollView(this);
        chat = new LinearLayout(this);
        chat.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(chat);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        LinearLayout row = new LinearLayout(this);

        Button mic = new Button(this);
        mic.setText("Mic");
        mic.setOnClickListener(v -> listen());
        row.addView(mic);

        input = new EditText(this);
        input.setTextColor(Color.WHITE);
        input.setHintTextColor(Color.GRAY);
        input.setHint("Talk to IRAS...");
        input.setSingleLine(true);
        input.setOnEditorActionListener((v, actionId, event) -> {
            send();
            return true;
        });
        row.addView(input, new LinearLayout.LayoutParams(0, -2, 1));

        Button send = new Button(this);
        send.setText("Send");
        send.setOnClickListener(v -> send());
        row.addView(send);

        root.addView(row);

        status = tv("Ready", 12);
        status.setTextColor(Color.GRAY);
        root.addView(status);

        setContentView(root);
    }

    private void addMessage(String who, String text) {
        runOnUiThread(() -> {
            TextView v = tv(who + ": " + text, 16);
            v.setBackgroundColor(
                who.equals("You")
                    ? Color.rgb(37, 42, 56)
                    : Color.rgb(22, 26, 36)
            );

            LinearLayout.LayoutParams p =
                new LinearLayout.LayoutParams(-1, -2);
            p.setMargins(0, 6, 0, 6);
            chat.addView(v, p);
        });
    }

    private void showSettings() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(30, 10, 30, 0);

        EditText server = new EditText(this);
        server.setHint(DEFAULT_SERVER);
        server.setText(serverUrl());

        EditText token = new EditText(this);
        token.setHint("IRAS access token");
        token.setText(prefs.getString("token", ""));
        token.setInputType(
            InputType.TYPE_CLASS_TEXT |
            InputType.TYPE_TEXT_VARIATION_PASSWORD
        );

        box.addView(server);
        box.addView(token);

        new AlertDialog.Builder(this)
            .setTitle("IRAS Server")
            .setView(box)
            .setPositiveButton("Save", (d, w) -> {
                String url = server.getText().toString().trim();
                if (url.isEmpty()) {
                    url = DEFAULT_SERVER;
                }

                prefs.edit()
                    .putString("server", url.replaceAll("/$", ""))
                    .putString(
                        "token",
                        token.getText().toString().trim()
                    )
                    .apply();
            })
            .setNegativeButton("Cancel", null)
            .show();
    }

    private void send() {
        String text = input.getText().toString().trim();
        if (text.isEmpty()) {
            return;
        }

        String token = prefs.getString("token", "");
        if (token.isEmpty()) {
            showSettings();
            return;
        }

        stopVoice();

        input.setText("");
        addMessage("You", text);
        status.setText("IRAS is thinking...");

        new Thread(
            () -> request(serverUrl(), token, text)
        ).start();
    }

    private void request(
        String server,
        String token,
        String message
    ) {
        HttpURLConnection c = null;

        try {
            URL u = new URL(server + "/v1/chat");
            c = (HttpURLConnection) u.openConnection();

            c.setRequestMethod("POST");
            c.setConnectTimeout(20000);
            c.setReadTimeout(120000);
            c.setDoOutput(true);

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

            JSONObject body = new JSONObject();
            body.put("message", message);
            body.put("device_id", "android");

            try (OutputStream os = c.getOutputStream()) {
                os.write(
                    body.toString()
                        .getBytes(StandardCharsets.UTF_8)
                );
            }

            int code = c.getResponseCode();

            InputStream is =
                (code >= 200 && code < 300)
                    ? c.getInputStream()
                    : c.getErrorStream();

            String raw = readAll(is);

            if (code < 200 || code >= 300) {
                throw new RuntimeException(
                    "HTTP " + code + ": " + raw
                );
            }

            String reply =
                new JSONObject(raw)
                    .getString("response");

            addMessage("IRAS", reply);

            runOnUiThread(
                () -> status.setText(
                    "Generating IRAS voice..."
                )
            );

            requestVoice(
                server,
                token,
                reply
            );

        } catch (Exception e) {
            addMessage(
                "IRAS",
                "Connection error: " +
                e.getMessage()
            );

            runOnUiThread(
                () -> status.setText("Offline")
            );

        } finally {
            if (c != null) {
                c.disconnect();
            }
        }
    }

    private void requestVoice(
        String server,
        String token,
        String text
    ) {
        HttpURLConnection c = null;

        try {
            URL u = new URL(server + "/v1/tts");
            c = (HttpURLConnection) u.openConnection();

            c.setRequestMethod("POST");
            c.setConnectTimeout(20000);
            c.setReadTimeout(120000);
            c.setDoOutput(true);

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

            JSONObject body = new JSONObject();
            body.put("text", text);

            try (OutputStream os = c.getOutputStream()) {
                os.write(
                    body.toString()
                        .getBytes(StandardCharsets.UTF_8)
                );
            }

            int code = c.getResponseCode();

            if (code < 200 || code >= 300) {
                String error =
                    readAll(c.getErrorStream());

                throw new RuntimeException(
                    "Voice HTTP " +
                    code +
                    ": " +
                    error
                );
            }

            File file = File.createTempFile(
                "iras_voice_",
                ".mp3",
                getCacheDir()
            );

            try (
                InputStream is = c.getInputStream();
                FileOutputStream fos =
                    new FileOutputStream(file)
            ) {
                byte[] buf = new byte[8192];
                int n;

                while ((n = is.read(buf)) != -1) {
                    fos.write(buf, 0, n);
                }
            }

            runOnUiThread(
                () -> playVoice(file)
            );

        } catch (Exception e) {
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

    private void playVoice(File file) {
        stopVoice();

        voiceFile = file;
        player = new MediaPlayer();

        try {
            player.setDataSource(
                file.getAbsolutePath()
            );

            player.setOnPreparedListener(
                mp -> {
                    status.setText(
                        "IRAS is speaking..."
                    );
                    mp.start();
                }
            );

            player.setOnCompletionListener(
                mp -> {
                    status.setText("Ready");
                    stopVoice();
                }
            );

            player.setOnErrorListener(
                (mp, what, extra) -> {
                    status.setText(
                        "Voice playback failed"
                    );
                    stopVoice();
                    return true;
                }
            );

            player.prepareAsync();

        } catch (Exception e) {
            status.setText(
                "Voice playback failed"
            );
            stopVoice();
        }
    }

    private void stopVoice() {
        if (player != null) {
            try {
                if (player.isPlaying()) {
                    player.stop();
                }
            } catch (Exception ignored) {}

            try {
                player.release();
            } catch (Exception ignored) {}

            player = null;
        }

        if (voiceFile != null) {
            try {
                voiceFile.delete();
            } catch (Exception ignored) {}

            voiceFile = null;
        }
    }

    private String readAll(
        InputStream is
    ) throws IOException {
        if (is == null) {
            return "";
        }

        ByteArrayOutputStream b =
            new ByteArrayOutputStream();

        byte[] x = new byte[4096];
        int n;

        while ((n = is.read(x)) != -1) {
            b.write(x, 0, n);
        }

        return new String(
            b.toByteArray(),
            StandardCharsets.UTF_8
        );
    }

    private void listen() {
        stopVoice();

        if (
            checkSelfPermission(
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                new String[]{
                    Manifest.permission.RECORD_AUDIO
                },
                7
            );
            return;
        }

        if (
            !SpeechRecognizer
                .isRecognitionAvailable(this)
        ) {
            status.setText(
                "Speech recognition is unavailable."
            );
            return;
        }

        if (recognizer == null) {
            recognizer =
                SpeechRecognizer
                    .createSpeechRecognizer(this);
        }

        recognizer.setRecognitionListener(
            new android.speech.RecognitionListener() {
                public void onReadyForSpeech(
                    Bundle b
                ) {
                    status.setText(
                        "Listening..."
                    );
                }

                public void onBeginningOfSpeech() {}
                public void onRmsChanged(float r) {}
                public void onBufferReceived(byte[] b) {}

                public void onEndOfSpeech() {
                    status.setText(
                        "Thinking..."
                    );
                }

                public void onError(int e) {
                    status.setText(
                        "Mic error " + e
                    );
                }

                public void onResults(Bundle b) {
                    ArrayList<String> r =
                        b.getStringArrayList(
                            SpeechRecognizer
                                .RESULTS_RECOGNITION
                        );

                    if (
                        r != null &&
                        !r.isEmpty()
                    ) {
                        input.setText(
                            r.get(0)
                        );
                        send();
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
            RecognizerIntent.EXTRA_LANGUAGE,
            "en-US"
        );

        recognizer.startListening(i);
    }

    @Override protected void onDestroy() {
        stopVoice();

        if (recognizer != null) {
            recognizer.destroy();
        }

        super.onDestroy();
    }
}
