# instagram_business_manage_messages — 설명 박스 복붙용

App overview
KLOW (operated by WELKIT) is a K-beauty commerce platform. A brand connects its own
Instagram professional account to the KLOW Brand dashboard. When users leave comments on the
brand's Instagram posts, the brand replies to those commenters by sending a private reply
(DM) that contains a link to the brand's KLOW storefront, turning commenters into storefront
visitors.

How instagram_business_manage_messages is used
We use instagram_business_manage_messages to send a private reply to a comment
(recipient = comment_id) on the connected professional account's own media. In the
"인스타그램" (Instagram) tab the brand opens a post, selects one or more comments, chooses a
message template under "메시지 템플릿" (Message templates) that includes its storefront link,
and clicks the "선택 N개에 DM 발송" (Send DM to N selected) button. We only send a private
reply once per comment and only within 7 days of the comment, per Instagram's rules. We do
NOT send unsolicited messages; every message is a reply to a user who commented on the
brand's own post. This permission works together with instagram_business_manage_comments (to
read the comments) and instagram_business_basic (to read the account profile and media).

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
4. Back in the "인스타그램" tab, open that post, select your comment, pick a template under
   "메시지 템플릿" (Message templates), and click "선택 N개에 DM 발송" (Send DM to N selected).
5. Your account receives the private reply (DM) with the brand's storefront link within ~30s.
