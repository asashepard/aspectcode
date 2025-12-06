// Should trigger: sec.open_redirect
function handleRedirect(req, res) {
    const url = req.query.url;
    res.redirect(url);
}
