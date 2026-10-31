/**
 * CareerQuest Frontend App & Swipe Handlers
 */

export function triggerSwipe(direction, card, appInstance) {
  const ctx = appInstance || (typeof window !== 'undefined' && window.__careerQuestApp);
  const targetCard = card || (ctx && ctx.swipeCard);
  if (direction === 'down') {
    if (ctx && typeof ctx.openPassFeedbackModal === 'function') {
      ctx.openPassFeedbackModal(targetCard);
    }
  } else if (direction === 'up') {
    if (ctx) {
      if (typeof ctx.exitSwipeMode === 'function') ctx.exitSwipeMode();
      if (typeof ctx.openJobStudioWithItem === 'function') ctx.openJobStudioWithItem(targetCard);
    }
  } else if (direction === 'left') {
    if (ctx && targetCard && targetCard.id && typeof ctx.rateDigestInterest === 'function') {
      ctx.rateDigestInterest(targetCard, -1);
    }
  } else if (direction === 'right') {
    if (ctx && targetCard && typeof ctx.addDigestToPipeline === 'function') {
      ctx.addDigestToPipeline(targetCard);
    }
  }
}

export function openDislikeModal(card, appInstance) {
  const ctx = appInstance || (typeof window !== 'undefined' && window.__careerQuestApp);
  if (ctx && typeof ctx.openPassFeedbackModal === 'function') {
    ctx.openPassFeedbackModal(card);
  }
}

export function openSwipeDetailsModal(card, appInstance) {
  const ctx = appInstance || (typeof window !== 'undefined' && window.__careerQuestApp);
  if (ctx) {
    if (typeof ctx.exitSwipeMode === 'function') ctx.exitSwipeMode();
    if (typeof ctx.openJobStudioWithItem === 'function') ctx.openJobStudioWithItem(card);
  }
}

export function openPassFeedbackModal(card, appInstance) {
  const ctx = appInstance || (typeof window !== 'undefined' && window.__careerQuestApp);
  if (ctx) {
    ctx.dislikeModalOpen = false;
    if (card && card.id && typeof ctx.rateDigestInterest === 'function') {
      ctx.rateDigestInterest(card, -1);
    }
  }
}

export function exitSwipeMode(appInstance) {
  const ctx = appInstance || (typeof window !== 'undefined' && window.__careerQuestApp);
  if (ctx) {
    ctx.dislikeModalOpen = false;
    ctx.swipeDetailsOpen = false;
  }
}

export function openJobStudioWithItem(card, appInstance) {
  const ctx = appInstance || (typeof window !== 'undefined' && window.__careerQuestApp);
  if (ctx && card && typeof ctx.openJobStudio === 'function') {
    ctx.openJobStudio(card);
  }
}

// Clean deduplicated touch listeners utility
export function setupSwipeTouchListeners(element, onSwipe) {
  if (!element || !onSwipe) return () => {};
  let startX = 0, startY = 0;
  
  const handleTouchStart = (e) => {
    if (e.touches && e.touches[0]) {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    }
  };
  
  const handleTouchEnd = (e) => {
    if (!e.changedTouches || !e.changedTouches[0]) return;
    const diffX = e.changedTouches[0].clientX - startX;
    const diffY = e.changedTouches[0].clientY - startY;
    if (Math.abs(diffX) > Math.abs(diffY)) {
      if (Math.abs(diffX) > 50) onSwipe(diffX > 0 ? 'right' : 'left');
    } else {
      if (Math.abs(diffY) > 50) onSwipe(diffY > 0 ? 'down' : 'up');
    }
  };

  element.addEventListener('touchstart', handleTouchStart, { passive: true });
  element.addEventListener('touchend', handleTouchEnd, { passive: true });

  return () => {
    element.removeEventListener('touchstart', handleTouchStart);
    element.removeEventListener('touchend', handleTouchEnd);
  };
}
