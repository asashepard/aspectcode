// Should trigger: sec.open_redirect
import { Request, Response } from 'express';

function handleRedirect(req: Request, res: Response) {
    const url = req.query.url as string;
    res.redirect(url);
}
