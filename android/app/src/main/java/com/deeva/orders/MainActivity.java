package com.deeva.orders;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.util.Base64;
import android.provider.MediaStore;
import android.speech.RecognizerIntent;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import com.google.firebase.messaging.FirebaseMessaging;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;

import java.util.ArrayList;
import java.util.List;

/**
 * Deeva Orders — a thin Android shell around the Deeva Orders web app.
 * The app (and every update to it) is served from the web, so this APK rarely needs reinstalling.
 * Native extras: speech-to-text (Google voice typing), camera / gallery picker, mic for voice notes, notifications.
 */
public class MainActivity extends Activity {
    private static final String CHANNEL = "orders";
    private static final int REQ_FILE = 11;
    private static final int REQ_SPEECH = 12;
    private static final int REQ_MIC = 13;
    private static final int REQ_NOTIF = 14;

    private WebView web;
    private String appUrl;
    private String appHost;
    private volatile boolean foreground = false;
    private int notifId = 100;

    private ValueCallback<Uri[]> fileCallback;
    private Uri cameraUri;
    private PermissionRequest pendingMic;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        appUrl = getString(R.string.app_url);
        appHost = Uri.parse(appUrl).getHost();

        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setCacheMode(isOnline() ? WebSettings.LOAD_DEFAULT : WebSettings.LOAD_CACHE_ELSE_NETWORK);
        s.setUserAgentString(s.getUserAgentString() + " DeevaOrdersApp/1");

        web.addJavascriptInterface(new Bridge(), "DeevaApp");
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                return openPicker(callback, params);
            }

            @Override
            public void onPermissionRequest(final PermissionRequest request) {
                runOnUiThread(() -> handleWebPermission(request));
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                String scheme = u.getScheme();
                if (("https".equals(scheme) || "http".equals(scheme)) && appHost != null && appHost.equalsIgnoreCase(u.getHost())) {
                    return false;
                }
                openExternal(u);
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    view.loadUrl("file:///android_asset/offline.html");
                }
            }
        });
        web.setDownloadListener((url, ua, cd, mime, len) -> openExternal(Uri.parse(url)));

        createChannel();
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIF);
        }

        if (state != null) {
            web.restoreState(state);
        } else {
            web.loadUrl(appUrl);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        foreground = true;
    }

    @Override
    protected void onPause() {
        foreground = false;
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        // let the page close an open dialog first
        web.evaluateJavascript("window.__doBack ? window.__doBack() : false", value -> {
            if ("true".equals(value)) return;
            if (web.canGoBack()) web.goBack();
            else finish();
        });
    }

    @Override
    protected void onDestroy() {
        if (web != null) web.destroy();
        super.onDestroy();
    }

    private boolean isOnline() {
        try {
            ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            NetworkInfo ni = cm == null ? null : cm.getActiveNetworkInfo();
            return ni != null && ni.isConnected();
        } catch (Exception e) {
            return true;
        }
    }

    private void openExternal(Uri u) {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, u);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
        } catch (Exception e) {
            Toast.makeText(this, R.string.link_failed, Toast.LENGTH_SHORT).show();
        }
    }

    /* ---------- photo / video picker with camera ---------- */
    private boolean openPicker(ValueCallback<Uri[]> callback, WebChromeClient.FileChooserParams params) {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        fileCallback = callback;
        cameraUri = null;
        String accept = "";
        String[] types = params.getAcceptTypes();
        if (types != null && types.length > 0 && types[0] != null) accept = types[0];
        boolean wantsImage = accept.startsWith("image");
        boolean wantsVideo = accept.startsWith("video");

        Intent content = new Intent(Intent.ACTION_GET_CONTENT);
        content.addCategory(Intent.CATEGORY_OPENABLE);
        content.setType(accept.isEmpty() ? "*/*" : accept);
        if (params.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
            content.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }

        List<Intent> extra = new ArrayList<>();
        if (wantsImage && Build.VERSION.SDK_INT >= 29) {
            try {
                ContentValues cv = new ContentValues();
                cv.put(MediaStore.Images.Media.DISPLAY_NAME, "deeva_" + System.currentTimeMillis() + ".jpg");
                cv.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                cv.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/Deeva Orders");
                cameraUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cv);
                if (cameraUri != null) {
                    Intent cam = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    cam.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri);
                    cam.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                    extra.add(cam);
                }
            } catch (Exception ignored) {
                cameraUri = null;
            }
        }
        if (wantsVideo) {
            extra.add(new Intent(MediaStore.ACTION_VIDEO_CAPTURE));
        }

        Intent chooser = Intent.createChooser(content, getString(R.string.pick_file));
        if (!extra.isEmpty()) chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, extra.toArray(new Intent[0]));
        try {
            startActivityForResult(chooser, REQ_FILE);
            return true;
        } catch (ActivityNotFoundException e) {
            fileCallback = null;
            dropCameraUri();
            return false;
        }
    }

    private void dropCameraUri() {
        if (cameraUri != null) {
            try { getContentResolver().delete(cameraUri, null, null); } catch (Exception ignored) { }
            cameraUri = null;
        }
    }

    /* ---------- speech to text ---------- */
    private void startSpeech(String lang) {
        Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang == null || lang.isEmpty() ? "hi-IN" : lang);
        i.putExtra(RecognizerIntent.EXTRA_PROMPT, getString(R.string.speak_now));
        i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        try {
            startActivityForResult(i, REQ_SPEECH);
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, R.string.no_speech, Toast.LENGTH_LONG).show();
            sendSpeech("");
        }
    }

    private void sendSpeech(String text) {
        final String js = "window.__doSpeech && window.__doSpeech(" + JSONObject.quote(text == null ? "" : text) + ")";
        runOnUiThread(() -> web.evaluateJavascript(js, null));
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQ_SPEECH) {
            String text = "";
            if (resultCode == RESULT_OK && data != null) {
                ArrayList<String> r = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
                if (r != null && !r.isEmpty()) text = r.get(0);
            }
            sendSpeech(text);
            return;
        }
        if (requestCode == REQ_FILE) {
            if (fileCallback == null) return;
            Uri[] result = null;
            if (resultCode == RESULT_OK) {
                if (data != null && data.getClipData() != null) {
                    ClipData cd = data.getClipData();
                    result = new Uri[cd.getItemCount()];
                    for (int i = 0; i < cd.getItemCount(); i++) result[i] = cd.getItemAt(i).getUri();
                } else if (data != null && data.getData() != null) {
                    result = new Uri[]{data.getData()};
                } else if (cameraUri != null) {
                    result = new Uri[]{cameraUri};
                }
            }
            if (result == null || (cameraUri != null && !containsUri(result, cameraUri))) dropCameraUri();
            fileCallback.onReceiveValue(result);
            fileCallback = null;
            cameraUri = null;
        }
    }

    private static boolean containsUri(Uri[] list, Uri u) {
        for (Uri x : list) if (u.equals(x)) return true;
        return false;
    }

    /* ---------- microphone for voice notes ---------- */
    private void handleWebPermission(PermissionRequest request) {
        boolean wantsAudio = false;
        for (String r : request.getResources()) {
            if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) wantsAudio = true;
        }
        if (!wantsAudio) {
            request.deny();
            return;
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            if (pendingMic != null) pendingMic.deny();
            pendingMic = request;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == REQ_MIC && pendingMic != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                pendingMic.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            } else {
                pendingMic.deny();
            }
            pendingMic = null;
        }
    }

    /* ---------- notifications ---------- */
    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription(getString(R.string.channel_desc));
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    @SuppressWarnings("deprecation")
    private void showNotification(String title, String body) {
        try {
            Intent i = new Intent(this, MainActivity.class);
            i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent pi = PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification.Builder nb = Build.VERSION.SDK_INT >= 26
                    ? new Notification.Builder(this, CHANNEL)
                    : new Notification.Builder(this);
            nb.setSmallIcon(R.drawable.ic_stat)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setStyle(new Notification.BigTextStyle().bigText(body))
                    .setAutoCancel(true)
                    .setContentIntent(pi);
            if (Build.VERSION.SDK_INT < 26) {
                nb.setPriority(Notification.PRIORITY_HIGH).setDefaults(Notification.DEFAULT_ALL);
            }
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.notify(notifId++, nb.build());
        } catch (Exception ignored) {
        }
    }

    /* ---------- receipt PDF: save to Downloads, then open WhatsApp (client's chat) or the share sheet ---------- */
    private Uri savePdf(String b64, String name) throws Exception {
        byte[] data = Base64.decode(b64, Base64.DEFAULT);
        String safe = name.replaceAll("[^A-Za-z0-9._-]", "_");
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.Downloads.DISPLAY_NAME, safe);
            cv.put(MediaStore.Downloads.MIME_TYPE, "application/pdf");
            cv.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Deeva Orders");
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) throw new Exception("no uri");
            try (OutputStream os = getContentResolver().openOutputStream(uri)) {
                if (os == null) throw new Exception("no stream");
                os.write(data);
            }
            return uri;
        }
        File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        File f = new File(dir, safe);
        try (FileOutputStream fo = new FileOutputStream(f)) { fo.write(data); }
        Toast.makeText(this, getString(R.string.pdf_saved) + " " + f.getAbsolutePath(), Toast.LENGTH_LONG).show();
        return null;
    }

    private Intent pdfIntent(Uri uri, String text) {
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("application/pdf");
        send.putExtra(Intent.EXTRA_STREAM, uri);
        if (text != null && !text.isEmpty()) send.putExtra(Intent.EXTRA_TEXT, text);
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        return send;
    }

    private boolean installed(String pkg) {
        try { getPackageManager().getPackageInfo(pkg, 0); return true; } catch (Exception e) { return false; }
    }

    private void savePdfAndShare(String b64, String name, String text) {
        try {
            Uri uri = savePdf(b64, name);
            if (uri != null) startActivity(Intent.createChooser(pdfIntent(uri, text), name));
        } catch (Exception e) {
            Toast.makeText(this, R.string.pdf_failed, Toast.LENGTH_LONG).show();
        }
    }

    /** Opens the client's chat in WhatsApp Business (or WhatsApp) with the PDF attached; falls back to the share sheet. */
    private void savePdfAndWhatsApp(String b64, String name, String text, String phone) {
        try {
            Uri uri = savePdf(b64, name);
            if (uri == null) return;
            String pkg = installed("com.whatsapp.w4b") ? "com.whatsapp.w4b" : (installed("com.whatsapp") ? "com.whatsapp" : null);
            if (pkg != null) {
                Intent send = pdfIntent(uri, text);
                send.setPackage(pkg);
                String digits = phone == null ? "" : phone.replaceAll("[^0-9]", "");
                if (digits.length() == 10) digits = "91" + digits;
                if (digits.length() >= 11) send.putExtra("jid", digits + "@s.whatsapp.net");
                try {
                    startActivity(send);
                    return;
                } catch (ActivityNotFoundException ignored) {
                    // fall through to the share sheet
                }
            }
            startActivity(Intent.createChooser(pdfIntent(uri, text), name));
        } catch (Exception e) {
            Toast.makeText(this, R.string.pdf_failed, Toast.LENGTH_LONG).show();
        }
    }

    /** Methods the web app can call as window.DeevaApp.* */
    private class Bridge {
        @JavascriptInterface
        public boolean isApp() {
            return true;
        }

        @JavascriptInterface
        public boolean isForeground() {
            return foreground;
        }

        @JavascriptInterface
        public void notifyUser(final String title, final String body) {
            runOnUiThread(() -> showNotification(title, body));
        }

        @JavascriptInterface
        public void copy(final String text) {
            runOnUiThread(() -> {
                ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("Deeva Orders", text));
            });
        }

        /** Speech to text; the result comes back through window.__doSpeech(text). */
        @JavascriptInterface
        public void listen(final String lang) {
            runOnUiThread(() -> startSpeech(lang));
        }

        @JavascriptInterface
        public void sharePdf(final String b64, final String name, final String text) {
            runOnUiThread(() -> savePdfAndShare(b64, name, text));
        }

        @JavascriptInterface
        public void sharePdfWhatsApp(final String b64, final String name, final String text, final String phone) {
            runOnUiThread(() -> savePdfAndWhatsApp(b64, name, text, phone));
        }

        /** Asks Firebase for this phone's notification address and hands it to the page (window.__doPushToken). */
        @JavascriptInterface
        public void requestPushToken() {
            try {
                FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
                    if (!task.isSuccessful() || task.getResult() == null) return;
                    final String js = "window.__doPushToken && window.__doPushToken(" + JSONObject.quote(task.getResult()) + ")";
                    runOnUiThread(() -> web.evaluateJavascript(js, null));
                });
            } catch (Exception ignored) {
                // push not configured yet (no google-services.json)
            }
        }

        @JavascriptInterface
        public void retry() {
            runOnUiThread(() -> {
                web.getSettings().setCacheMode(isOnline() ? WebSettings.LOAD_DEFAULT : WebSettings.LOAD_CACHE_ELSE_NETWORK);
                web.loadUrl(appUrl);
            });
        }
    }
}
