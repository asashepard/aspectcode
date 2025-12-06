// Should trigger: sec.open_redirect
import javax.servlet.http.*;

public class RedirectHandler {
    public void handleRedirect(HttpServletRequest request, HttpServletResponse response) throws Exception {
        String url = request.getParameter("url");
        response.sendRedirect(url);  // Open redirect vulnerability!
    }
}
