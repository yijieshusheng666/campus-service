"""创建 / 提升一个平台管理员账号。

用法（在 backend/ 目录下，用项目的虚拟环境执行）：

    # 自动生成 16 位随机密码
    .venv/bin/python scripts/create_admin.py admin admin@example.com

    # 自己指定密码（注意：会留在 shell 历史里）
    .venv/bin/python scripts/create_admin.py admin admin@example.com 'MyPass123'

    # 把已有的普通用户提升为管理员（不改密码）
    .venv/bin/python scripts/create_admin.py --promote 某个用户名

设计说明：

1. **这个脚本只从服务器命令行执行，刻意不暴露成 HTTP 接口。**
   「管理员互相提权」是最经典的一类权限漏洞：只要后台有一个「设为管理员」
   按钮，攻破任意一个管理员账号就等于能无限造管理员。把入口放在
   「必须能登上服务器」这一层，攻击面小得多。

2. **幂等**：账号已存在就原地提升，不报错、不覆盖密码。
   重复执行是安全的。

3. 密码由脚本现场生成、只打印一次，避免「看截图手抄密码」这类低级错误。
"""
import argparse
import asyncio
import secrets
import string
import sys
from pathlib import Path

# 直接 `python scripts/create_admin.py` 执行时，sys.path 里只有 scripts/ 目录，
# 找不到 app 包。这里显式把 backend/（脚本的上级目录）加进去。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def gen_password(length: int = 16) -> str:
    """生成纯字母数字密码。

    刻意不含特殊符号：这些字符在 shell 引号、.env 文件、命令行参数里
    都需要转义，是「明明密码对却连不上」的高发区。
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="创建或提升平台管理员账号",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("username", nargs="?", help="用户名")
    parser.add_argument("email", nargs="?", help="邮箱（仅新建时需要，提升已有用户时可省略）")
    parser.add_argument("password", nargs="?", help="密码；省略则自动生成随机密码")
    parser.add_argument(
        "--promote", metavar="USERNAME", help="把已存在的用户提升为管理员，不改动其密码"
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        # ---- 模式一：提升已有用户 ----
        if args.promote:
            user = (
                await db.execute(select(User).where(User.username == args.promote))
            ).scalar_one_or_none()
            if not user:
                print(f"[失败] 找不到用户 {args.promote!r}，先用「注册」页面把它建出来", file=sys.stderr)
                return 1
            user.is_admin = True
            user.is_active = True
            await db.commit()
            print(f"[完成] {user.username}（id={user.id}）已提升为管理员，密码未改动")
            return 0

        # ---- 模式二：新建（或已存在则提升）----
        if not args.username or not args.email:
            parser.error("需要同时提供 username 和 email，或改用 --promote 用户名")

        user = (
            await db.execute(select(User).where(User.username == args.username))
        ).scalar_one_or_none()

        if user:
            user.is_admin = True
            user.is_active = True
            await db.commit()
            print(f"[完成] {user.username}（id={user.id}）已存在，已提升为管理员，密码未改动")
            return 0

        password = args.password or gen_password()
        user = User(
            username=args.username,
            email=args.email,
            hashed_password=hash_password(password),
            nickname="平台管理员",
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            print(
                f"[失败] 邮箱 {args.email!r} 已被其他账号占用。换一个邮箱，"
                f"或用 --promote 提升已有账号。",
                file=sys.stderr,
            )
            return 1
        await db.refresh(user)

        print("=" * 54)
        print("  管理员账号创建成功")
        print("=" * 54)
        print(f"  用户名   {user.username}")
        print(f"  密码     {password}")
        print(f"  用户 ID  {user.id}")
        print("=" * 54)
        print("  密码只显示这一次，请立刻复制保存到密码管理器。")
        print("  登录后左侧菜单最下方会出现「管理后台」入口。")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
