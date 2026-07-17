package com.gojek.consumer.gmt.gofood;

// SECONDARY output (coded GMT) — emitted only where NLP can't express the case, or target_framework=GMT.
// Primary output for these scenarios is the TapMind NLP file. Shown here for parity/reference.
// Locators resolve per platform from change_context (android=resource-id, ios=accessibilityId).

import com.gojek.consumer.gmt.base.BaseMobileTest;        // existing GMT base (Appium driver setup)
import com.gojek.consumer.gmt.pages.gofood.CartReviewPage; // existing/extended page object
import com.gojek.consumer.gmt.data.TestDataClient;         // wraps the Test-Data Provisioner (TestBuddy)
import org.testng.annotations.Test;
import static org.testng.Assert.*;

public class GoFoodCheckoutPromoTest extends BaseMobileTest {

    private CartReviewPage cart;

    // SC-001 — REQ-1 — P0 — happy
    @Test(groups = {"P0"}, description = "SC-001 REQ-1: valid SAVE20 reduces cart total and charged amount")
    public void validSave20ReducesTotal() {
        var consumer = TestDataClient.consumer().segment("first_time_gofood").payment("gopay").lease(); // DN-1
        TestDataClient.gopay(consumer).rechargeAtLeast(orderTotal());                                    // DN-2
        TestDataClient.voucher("SAVE20").ensureValid();                                                  // DN-3
        cart = openDeeplink("gojek://food/cart/review", CartReviewPage.class);                           // nav via HOOK-DL-CART
        long before = cart.getCartTotal();
        cart.enterPromo("SAVE20").apply();
        assertTrue(cart.getCartTotal() < before, "Total should drop after a valid promo");
        assertEquals(cart.confirmAndGetCharged(), cart.getCartTotal(), "Charged == displayed discounted total");
    }

    // SC-002 — REQ-1 — P0 — negative (insufficient balance)
    @Test(groups = {"P0"}, description = "SC-002 REQ-1: insufficient GoPay balance → cannot apply, total unchanged")
    public void insufficientBalanceBlocksPromo() {
        var consumer = TestDataClient.consumer().segment("first_time_gofood").payment("gopay").lease();
        TestDataClient.gopay(consumer).setBalance(orderTotal() - 1);   // boundary: required-1
        cart = openDeeplink("gojek://food/cart/review", CartReviewPage.class);
        long before = cart.getCartTotal();
        cart.enterPromo("SAVE20").apply();
        assertTrue(cart.isPromoErrorVisible(), "Error expected on insufficient balance");
        assertEquals(cart.getCartTotal(), before, "Total unchanged when promo rejected");
    }
}
