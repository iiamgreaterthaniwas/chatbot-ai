package xyz.photoidmaker.dumplings

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.view.View
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.ProgressBar
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import java.io.File

/**
 * 饺子 App：用 WebView 全屏打开网站，页面和功能都来自服务器，
 * 这里只处理 App 才需要的事情：选图/拍照、返回键、外部链接、断网提示、登录状态保存。
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var errorView: View

    private val appHost: String? = Uri.parse(BuildConfig.APP_URL).host

    // 网页里点"添加图片"时，等用户选完再把结果交回给网页
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private var cameraFile: File? = null

    private val chooseImages = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val callback = filePathCallback ?: return@registerForActivityResult
        filePathCallback = null
        callback.onReceiveValue(if (result.resultCode == RESULT_OK) pickedUris(result.data) else null)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.web_view)
        progressBar = findViewById(R.id.progress)
        errorView = findViewById(R.id.error_view)
        findViewById<Button>(R.id.retry).setOnClickListener { retry() }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true          // 深色模式等设置存在 localStorage 里
            allowFileAccess = false
            allowContentAccess = true         // 选中的图片以 content:// 形式交给网页
            setSupportZoom(false)
            builtInZoomControls = false
            // 在 UA 后面加个标记，网页需要时可以判断是不是在 App 里打开
            userAgentString = "$userAgentString JiaoziApp/${BuildConfig.VERSION_NAME}"
        }
        CookieManager.getInstance().setAcceptCookie(true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                // 自己网站的页面在 App 里打开，其他链接（比如获取 API Key）交给手机浏览器
                if (uri.host == appHost && (uri.scheme == "https" || uri.scheme == "http")) return false
                openExternal(uri)
                return true
            }

            override fun onPageFinished(view: WebView, url: String?) {
                // 及时把登录 cookie 写到磁盘，下次打开不用重新登录
                CookieManager.getInstance().flush()
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) errorView.visibility = View.VISIBLE
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility = if (newProgress < 100) View.VISIBLE else View.GONE
            }

            override fun onShowFileChooser(
                view: WebView,
                callback: ValueCallback<Array<Uri>>,
                params: WebChromeClient.FileChooserParams
            ): Boolean {
                filePathCallback?.onReceiveValue(null)
                filePathCallback = callback
                return try {
                    chooseImages.launch(buildImageChooser(params.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE))
                    true
                } catch (e: ActivityNotFoundException) {
                    filePathCallback = null
                    false
                }
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // 先让网页关闭大图、弹窗、侧边栏；网页没有可关的再退出 App
                webView.evaluateJavascript("window.jiaoziHandleBack ? window.jiaoziHandleBack() : false") { handled ->
                    if (handled != "true") finish()
                }
            }
        })

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(BuildConfig.APP_URL)
        }
    }

    private fun retry() {
        errorView.visibility = View.GONE
        if (webView.url.isNullOrEmpty()) webView.loadUrl(BuildConfig.APP_URL) else webView.reload()
    }

    private fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (e: ActivityNotFoundException) {
            // 手机上没有能打开这个链接的 App，忽略
        }
    }

    /** 弹出"选择图片"，同时提供"拍照"选项 */
    private fun buildImageChooser(allowMultiple: Boolean): Intent {
        val pick = Intent(Intent.ACTION_GET_CONTENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, allowMultiple)
        }
        val chooser = Intent.createChooser(pick, getString(R.string.choose_image))
        createCameraIntent()?.let { chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, arrayOf(it)) }
        return chooser
    }

    private fun createCameraIntent(): Intent? {
        cameraFile = null
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        if (intent.resolveActivity(packageManager) == null) return null
        val dir = File(cacheDir, "camera").apply { mkdirs() }
        dir.listFiles()?.forEach { it.delete() }  // 清掉上一次拍的照片
        val file = File(dir, "photo_${System.currentTimeMillis()}.jpg")
        cameraFile = file
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        return intent
            .putExtra(MediaStore.EXTRA_OUTPUT, uri)
            .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }

    private fun pickedUris(data: Intent?): Array<Uri>? {
        val clip = data?.clipData
        if (clip != null && clip.itemCount > 0) return Array(clip.itemCount) { clip.getItemAt(it).uri }
        data?.data?.let { return arrayOf(it) }
        // 拍照的结果不在 data 里，而是直接写进了我们给的文件
        val photo = cameraFile
        if (photo != null && photo.exists() && photo.length() > 0) {
            return arrayOf(FileProvider.getUriForFile(this, "$packageName.fileprovider", photo))
        }
        return null
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        webView.saveState(outState)
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        CookieManager.getInstance().flush()
        webView.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}
