package com.darkness.iras;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.util.ArrayList;

/**
 * The new IRAS screen. It shows the same Command Center page as the website,
 * so the phone, the PC and the browser always look the same.
 *
 * The first version of this app (its own native screen with hands-free mode and
 * companion notices) is still inside the app as ClassicActivity.
 */
public class MainActivity extends Activity {
    private static final String DEFAULT_SERVER = "https://iras-cloud.onrender.com";
    private static final int MIC_PERMISSION = 7;
    private static final String BACKGROUND = "#04070F";
    private static final String OFFLINE_HTML =
        "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
        + "<body style='margin:0;background:#04070F;color:#e8f0ff;font-family:sans-serif;"
        + "display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center'>"
        + "<div style='padding:24px'><h2>Cannot reach IRAS</h2>"
        + "<p style='opacity:.75'>Check your internet. If the server was asleep, wait a minute and try again.</p>"
        + "<p><button style='font-size:18px;padding:12px 22px;border-radius:12px;border:0;background:#2ee6a6' "
        + "onclick='IRASNative.reload()'>Try again</button></p>"
        + "<p><button style='font-size:15px;padding:10px 18px;border-radius:12px;border:1px solid #4a5a78;"
        + "background:transparent;color:#e8f0ff' onclick='IRASNative.openClassic()'>Open the classic screen</button></p>"
        + "</div></body></html>";

    private WebView web;
    private SharedPreferences prefs;
    private SpeechRecognizer recognizer;
    private String pendingLanguage = "";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("iras", MODE_PRIVATE);
        getWindow().setStatusBarColor(Color.parseColor(BACKGROUND));
        getWindow().setNavigationBarColor(Color.parseColor(BACKGROUND));

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor(BACKGROUND));
        setContentView(web);

        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " IRASApp/1");
        web.addJavascriptInterface(new Bridge(), "IRASNative");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri target = request.getUrl();
                String host = Uri.parse(server()).getHost();
                if (host != null && host.equalsIgnoreCase(target.getHost())) {
                    return false;
                }
                startActivity(new Intent(Intent.ACTION_VIEW, target));
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    view.loadData(OFFLINE_HTML, "text/html", "UTF-8");
                }
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> request.grant(request.getResources()));
            }
        });

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, MIC_PERMISSION);
        }
        loadPage();
    }

    private String server() {
        String saved = prefs.getString("server", DEFAULT_SERVER);
        String value = saved == null || saved.trim().isEmpty() ? DEFAULT_SERVER : saved.trim();
        while (value.endsWith("/")) {
            value = value.substring(0, value.length() - 1);
        }
        return value;
    }

    /** The token is passed in the part of the address after the #, which the server never sees. */
    private void loadPage() {
        String token = prefs.getString("token", "");
        String url = server() + "/";
        if (token != null && !token.isEmpty()) {
            url += "#token=" + Uri.encode(token);
        }
        web.loadUrl(url);
    }

    private void emit(String type, String text) {
        try {
            JSONObject event = new JSONObject();
            event.put("type", type);
            event.put("text", text == null ? "" : text);
            final String script = "window.IRASNativeSpeech&&window.IRASNativeSpeech.event(" + event.toString() + ")";
            runOnUiThread(() -> web.evaluateJavascript(script, null));
        } catch (Exception ignored) {
            // nothing to tell the page
        }
    }

    private void startListening(String language) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            pendingLanguage = language == null ? "" : language;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, MIC_PERMISSION);
            return;
        }
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(this);
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) { }
                @Override public void onBeginningOfSpeech() { }
                @Override public void onRmsChanged(float rmsdB) { }
                @Override public void onBufferReceived(byte[] buffer) { }
                @Override public void onEndOfSpeech() { }
                @Override public void onEvent(int eventType, Bundle params) { }

                @Override
                public void onError(int error) {
                    emit("error", String.valueOf(error));
                    emit("end", "");
                }

                @Override
                public void onPartialResults(Bundle partialResults) {
                    ArrayList<String> list = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (list != null && !list.isEmpty()) {
                        emit("partial", list.get(0));
                    }
                }

                @Override
                public void onResults(Bundle results) {
                    ArrayList<String> list = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (list != null && !list.isEmpty()) {
                        emit("final", list.get(0));
                    }
                    emit("end", "");
                }
            });
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        if (language != null && !language.isEmpty()) {
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, language);
        }
        recognizer.startListening(intent);
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != MIC_PERMISSION) {
            return;
        }
        boolean granted = grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED;
        if (granted && !pendingLanguage.isEmpty()) {
            String language = pendingLanguage;
            pendingLanguage = "";
            startListening(language);
        } else if (!granted) {
            emit("error", "9");
            emit("end", "");
        }
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (recognizer != null) {
            recognizer.destroy();
            recognizer = null;
        }
        web.destroy();
        super.onDestroy();
    }

    /** What the page can ask the phone to do. */
    private class Bridge {
        @JavascriptInterface
        public boolean canListen() {
            return SpeechRecognizer.isRecognitionAvailable(MainActivity.this);
        }

        @JavascriptInterface
        public void listen(final String language) {
            runOnUiThread(() -> startListening(language));
        }

        @JavascriptInterface
        public void stop() {
            runOnUiThread(() -> {
                if (recognizer != null) {
                    recognizer.stopListening();
                }
            });
        }

        @JavascriptInterface
        public void reload() {
            runOnUiThread(() -> loadPage());
        }

        @JavascriptInterface
        public void openClassic() {
            runOnUiThread(() -> startActivity(new Intent(MainActivity.this, ClassicActivity.class)));
        }
    }
}
