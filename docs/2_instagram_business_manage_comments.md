# instagram_business_manage_comments — 설명 박스 복붙용

> 붙여넣기 전에 [대괄호] 2곳(테스트 IG 핸들 / 공개 게시물 URL)을 채우세요.

App overview
KLOW (operated by WELKIT) is a K-beauty commerce platform. A brand connects its own
Instagram professional account to the KLOW Brand dashboard, reads the comments left on its
own Instagram posts, and replies to those commenters by sending a private reply (DM) that
contains a link to the brand's KLOW storefront.

How instagram_business_manage_comments is used
We use instagram_business_manage_comments to READ the comments on the connected professional
account's own media — each comment's id, text, timestamp, and the commenter's username. In
the "인스타그램" (Instagram) tab the brand opens a post to see its comment list; the
commenter's username is shown so the brand knows who it is replying to, and the comment id is
used as the recipient of the private reply. We only read comments on the brand's own posts.
This permission works together with instagram_business_basic (account profile and media) and
instagram_business_manage_messages (to send the private reply / DM).

Important: KLOW is NOT a keyword auto-responder. After a user comments, a brand operator
opens the dashboard, selects the comment, and sends the DM manually (human-in-the-loop). We
use the Private Replies API, so the reply appears in the commenter's Instagram inbox within
about 30 seconds of the comment.

Test post (connected to our app)
- Connected test Instagram professional account: @pibugom
- Public post to comment on: https://www.instagram.com/p/Dat-_1ZkhmU/
- No specific keyword is required — comment any text. For easy identification you may
  comment: "관심있어요" (I'm interested).

How to test (app credentials only — no Instagram credentials)
The Instagram professional account @pibugom is ALREADY connected to this test brand account,
so you do not need to connect anything — you can test immediately. The app UI and the
screencast are in Korean; exact labels are quoted below.
1. Open https://brand-staging.klow.kr and log in with the test brand account —
   Email: simsgood0807+5@gmail.com, Password: klowtest77!!
2. Click the "인스타그램" (Instagram) tab in the left menu. You will see the connected account
   @pibugom and a grid of its posts.
3. From your own Instagram account, leave a comment on this post:
   https://www.instagram.com/p/Dat-_1ZkhmU/
4. Back in the "인스타그램" tab, open that post — the comment list is displayed, showing each
   commenter's username (read via instagram_business_manage_comments).
5. Select your comment, choose a template under "메시지 템플릿" (Message templates), and click
   "선택 N개에 DM 발송" (Send DM to N selected). Your account receives the DM within ~30s.
