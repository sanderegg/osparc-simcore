/* ************************************************************************

   osparc - the simcore frontend

   https://osparc.io

   Copyright:
     2024 IT'IS Foundation, https://itis.swiss

   License:
     MIT: https://opensource.org/licenses/MIT

   Authors:
     * Odei Maiz (odeimaiz)

************************************************************************ */

qx.Class.define("osparc.vipMarket.Market", {
  extend: osparc.ui.window.TabbedView,

  construct: function(category) {
    this.base(arguments);

    const miniWallet = osparc.desktop.credits.BillingCenter.createMiniWalletView().set({
      paddingRight: 10,
      minWidth: 150,
    });
    this.addWidgetOnTopOfTheTabs(miniWallet);

    osparc.store.LicensedItems.getInstance().getLicensedItems()
      .then(() => {
        [{
          category: "human",
          label: "Humans",
          icon: "@FontAwesome5Solid/users/20",
          vipSubset: "HUMAN_BODY",
        }, {
          category: "human_region",
          label: "Humans (Region)",
          icon: "@FontAwesome5Solid/users/20",
          vipSubset: "HUMAN_BODY_REGION",
        }, {
          category: "animal",
          label: "Animals",
          icon: "@FontAwesome5Solid/users/20",
          vipSubset: "ANIMAL",
        }, {
          category: "phantom",
          label: "Phantoms",
          icon: "@FontAwesome5Solid/users/20",
          vipSubset: "PHANTOM",
        }].forEach(marketInfo => {
          this.__buildViPMarketPage(marketInfo);
        });

        if (category) {
          this.openCategory(category);
        }
      });
  },

  events: {
    "importMessageSent": "qx.event.type.Data",
  },

  properties: {
    openBy: {
      check: "String",
      init: null,
      nullable: true,
      event: "changeOpenBy",
    },
  },

  members: {
    __buildViPMarketPage: function(marketInfo) {
      const vipMarketView = new osparc.vipMarket.VipMarket();
      vipMarketView.set({
        vipSubset: marketInfo["vipSubset"],
      });
      this.bind("openBy", vipMarketView, "openBy");
      vipMarketView.addListener("importMessageSent", () => this.fireEvent("importMessageSent"));
      const page = this.addTab(marketInfo["label"], marketInfo["icon"], vipMarketView);
      page.category = marketInfo["category"];
      return page;
    },

    openCategory: function(category) {
      const viewFound = this.getChildControl("tabs-view").getChildren().find(view => view.category === category);
      if (viewFound) {
        this._openPage(viewFound);
        return true;
      }
      return false;
    },

    sendCloseMessage: function() {
      const store = osparc.store.Store.getInstance();
      const currentStudy = store.getCurrentStudy();
      const nodeId = this.getOpenBy();
      if (currentStudy && nodeId) {
        const msg = {
          "type": "closeMarket",
        };
        currentStudy.sendMessageToIframe(nodeId, msg);
      }
    },
  }
});
