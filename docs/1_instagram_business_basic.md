# instagram_business_basic — 설명 박스 복붙용

App overview
KLOW (operated by WELKIT) is a K-beauty commerce platform. A brand logs into the KLOW
Brand dashboard and connects its own Instagram professional account. After connecting, the
brand sees its own account profile and recent posts inside the dashboard, and can reply to
users who commented on those posts by sending a private reply (DM) that contains a link to
the brand's KLOW storefront.

How instagram_business_basic is used
We use instagram_business_basic to read the connected Instagram professional account's basic
profile (user_id, username) and its media (id, caption, media_url, permalink,
comments_count). The connected username is shown at the top of the "인스타그램" (Instagram)
tab to confirm which account is linked, and the media are shown as a grid of the brand's own
posts. This permission is requested as a DEPENDENT permission required by
instagram_business_manage_comments and instagram_business_manage_messages, which power our
comment-to-DM feature.

Test account (connected to our app)
- Connected test Instagram professional account: @pibugom
- Example public post: https://www.instagram.com/p/Dat-_1ZkhmU/

How to test (app credentials only — no Instagram credentials)
The Instagram professional account @pibugom is ALREADY connected to this test brand account,
so you do not need to connect anything — the profile and media are shown immediately. The app
UI and the screencast are in Korean; exact labels are quoted below.
1. Open https://brand-staging.klow.kr and log in with the test brand account —
   Email: simsgood0807+5@gmail.com, Password: klowtest77!!
2. Click the "인스타그램" (Instagram) tab in the left menu.
3. The tab shows the connected account's username (@pibugom) at the top and a grid of that
   account's posts — both loaded via instagram_business_basic.
4. Click any post to open its comments view, where the profile/username and media are also
   displayed.

Note: The screencast additionally shows the one-time connection flow (clicking
"인스타그램 계정 연동하기" / Connect Instagram account and signing in with Instagram Login) to
demonstrate how an Instagram professional account onboards to the app.
