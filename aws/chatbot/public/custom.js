/**
 * Prevents chatbot iframes from auto-scrolling or hijacking focus and jumping to the bottom of page
 * until the user first interacts with the page.
 */
(function() {
    let hasInteracted = false;

    // set flag and remove listeners on first interaction
    const onInteraction = () => {
        hasInteracted = true;
        events.forEach(e => window.removeEventListener(e, onInteraction, true));
    };

    const events = ['mousedown', 'keydown', 'touchstart'];
    events.forEach(e => window.addEventListener(e, onInteraction, true));

    // scrollIntoView: nearest to prevent jumps before interaction
    const originalScrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function(arg) {
        if (!hasInteracted) {
            return originalScrollIntoView.call(this, { block: 'nearest', inline: 'nearest' });
        }
        return originalScrollIntoView.apply(this, arguments);
    };

    // preventScroll before interaction
    const originalFocus = HTMLElement.prototype.focus;
    HTMLElement.prototype.focus = function(options) {
        if (!hasInteracted) {
            return originalFocus.call(this, { ...options, preventScroll: true });
        }
        return originalFocus.apply(this, arguments);
    };
})();