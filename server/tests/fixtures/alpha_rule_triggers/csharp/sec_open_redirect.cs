// Should trigger: sec.open_redirect
using Microsoft.AspNetCore.Mvc;

public class RedirectController : Controller {
    public IActionResult HandleRedirect(string url) {
        return Redirect(url);  // Open redirect!
    }
}
