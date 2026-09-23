# -*- coding: utf-8 -*-
"""Lock do corpo: UMA vida por corpo.

Duas infinite.py no mesmo diretorio = race condition (gen_NNN colidindo,
lineage/best sobrescrito no meio de leitura, ledger de gasto em
read-modify-write duplo). O lock recusa a segunda vida no boot.
fcntl no Linux (VPS); msvcrt no Windows (dev). Sem suporte: avisa e segue."""
from __future__ import annotations

import os


def acquire(root):
    """Retorna (ok, handle_ou_None, msg). ok=False = outro corpo vivo."""
    p = os.path.join(root, "guard", "body.lock")
    try:
        fh = open(p, "a+")  # nao trunca (o msvcrt precisa de bytes pra travar)
    except OSError as e:
        return True, None, "lock indisponivel (%s) — seguindo sem lock" % e
    try:
        fh.seek(0, 2)
        if fh.tell() == 0:
            fh.write("0")
            fh.flush()
        fh.seek(0)
        try:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        return True, fh, "lock adquirido (pid %d)" % os.getpid()
    except OSError:
        try:
            fh.close()
        except Exception:
            pass
        return False, None, "outro infinite.py ja vive neste corpo (ver guard/body.lock)"
    except Exception as e:
        try:
            fh.close()
        except Exception:
            pass
        return True, None, "lock indisponivel (%s) — seguindo sem lock" % e
