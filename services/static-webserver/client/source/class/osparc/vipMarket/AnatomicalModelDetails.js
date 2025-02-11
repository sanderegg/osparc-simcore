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

qx.Class.define("osparc.vipMarket.AnatomicalModelDetails", {
  extend: qx.ui.core.Widget,

  construct: function() {
    this.base(arguments);

    const layout = new qx.ui.layout.VBox(15);
    this._setLayout(layout);

    this.__populateLayout();
  },

  events: {
    "modelPurchaseRequested": "qx.event.type.Data",
    "modelImportRequested": "qx.event.type.Data",
  },

  properties: {
    openBy: {
      check: "String",
      init: null,
      nullable: true,
      event: "changeOpenBy",
    },

    anatomicalModelsData: {
      check: "Object",
      init: null,
      nullable: true,
      apply: "__populateLayout"
    },
  },

  members: {
    __populateLayout: function() {
      this._removeAll();

      const anatomicalModelsData = this.getAnatomicalModelsData();
      if (anatomicalModelsData && anatomicalModelsData["licensedResourceData"]) {
        const modelInfo = this.__createModelInfo(anatomicalModelsData["licensedResourceData"]["source"]);
        const pricingUnits = this.__createPricingUnits(anatomicalModelsData);
        const importButton = this.__createImportSection(anatomicalModelsData);
        this._add(modelInfo);
        this._add(pricingUnits);
        this._add(importButton);
      } else {
        const selectModelLabel = new qx.ui.basic.Label().set({
          value: this.tr("Select a model for more details"),
          font: "text-16",
          alignX: "center",
          alignY: "middle",
          allowGrowX: true,
          allowGrowY: true,
        });
        this._add(selectModelLabel);
      }
    },

    __createModelInfo: function(anatomicalModelsDataSource) {
      const cardLayout = new qx.ui.container.Composite(new qx.ui.layout.VBox(16));

      const description = anatomicalModelsDataSource["description"] || "";
      const delimiter = " - ";
      let titleAndSubtitle = description.split(delimiter);
      if (titleAndSubtitle.length > 0) {
        const titleLabel = new qx.ui.basic.Label().set({
          value: titleAndSubtitle[0],
          font: "text-16",
          alignY: "middle",
          allowGrowX: true,
          allowGrowY: true,
        });
        cardLayout.add(titleLabel);
        titleAndSubtitle.shift();
      }
      if (titleAndSubtitle.length > 0) {
        titleAndSubtitle = titleAndSubtitle.join(delimiter);
        const subtitleLabel = new qx.ui.basic.Label().set({
          value: titleAndSubtitle,
          font: "text-16",
          alignY: "middle",
          allowGrowX: true,
          allowGrowY: true,
        });
        cardLayout.add(subtitleLabel);
      }


      const middleLayout = new qx.ui.container.Composite(new qx.ui.layout.HBox(16));
      const thumbnail = new qx.ui.basic.Image().set({
        source: anatomicalModelsDataSource["thumbnail"],
        alignY: "middle",
        scale: true,
        allowGrowX: true,
        allowGrowY: true,
        allowShrinkX: true,
        allowShrinkY: true,
        maxWidth: 256,
        maxHeight: 256,
      });
      middleLayout.add(thumbnail);

      const features = anatomicalModelsDataSource["features"];
      const featuresGrid = new qx.ui.layout.Grid(8, 8);
      const featuresLayout = new qx.ui.container.Composite(featuresGrid);
      let idx = 0;
      [
        "Name",
        "Version",
        "Sex",
        "Age",
        "Weight",
        "Height",
        "Date",
        "Ethnicity",
        "Functionality",
      ].forEach(key => {
        if (key.toLowerCase() in features) {
          const titleLabel = new qx.ui.basic.Label().set({
            value: key,
            font: "text-14",
            alignX: "right",
          });
          featuresLayout.add(titleLabel, {
            column: 0,
            row: idx,
          });

          const nameLabel = new qx.ui.basic.Label().set({
            value: features[key.toLowerCase()],
            font: "text-14",
            alignX: "left",
          });
          featuresLayout.add(nameLabel, {
            column: 1,
            row: idx,
          });

          idx++;
        }
      });

      const doiTitle = new qx.ui.basic.Label().set({
        value: "DOI",
        font: "text-14",
        alignX: "right",
        marginTop: 16,
      });
      featuresLayout.add(doiTitle, {
        column: 0,
        row: idx,
      });

      const doiToLink = doi => {
        const doiLabel = new osparc.ui.basic.LinkLabel("-").set({
          font: "text-14",
          alignX: "left",
          marginTop: 16,
        });
        if (doi) {
          doiLabel.set({
            value: doi,
            url: "https://doi.org/" + doi,
            font: "link-label-14",
          });
        }
        return doiLabel;
      };
      featuresLayout.add(doiToLink(anatomicalModelsDataSource["doi"]), {
        column: 1,
        row: idx,
      });

      middleLayout.add(featuresLayout);

      cardLayout.add(middleLayout);

      return cardLayout;
    },

    __createPricingUnits: function(anatomicalModelsData) {
      const pricingUnitsLayout = new qx.ui.container.Composite(new qx.ui.layout.HBox(10).set({
        alignX: "center"
      }));

      osparc.store.Pricing.getInstance().fetchPricingUnits(anatomicalModelsData["pricingPlanId"])
        .then(pricingUnits => {
          pricingUnits.forEach(pricingUnit => {
            pricingUnit.set({
              classification: "LICENSE"
            });
            const pUnit = new osparc.study.PricingUnitLicense(pricingUnit).set({
              showRentButton: true,
            });
            pUnit.addListener("rentPricingUnit", () => {
              this.fireDataEvent("modelPurchaseRequested", {
                modelId: anatomicalModelsData["licensedResourceData"]["source"]["id"],
                licensedItemId: anatomicalModelsData["licensedItemId"],
                pricingPlanId: anatomicalModelsData["pricingPlanId"],
                pricingUnitId: pricingUnit.getPricingUnitId(),
              });
            }, this);
            pricingUnitsLayout.add(pUnit);
          });
        })
        .catch(err => console.error(err));

      return pricingUnitsLayout;
    },

    __createImportSection: function(anatomicalModelsData) {
      const importSection = new qx.ui.container.Composite(new qx.ui.layout.VBox(5).set({
        alignX: "center"
      }));

      anatomicalModelsData["purchases"].forEach(purchase => {
        const seatsText = "seat" + (purchase["numberOfSeats"] > 1 ? "s" : "");
        const entry = new qx.ui.basic.Label().set({
          value: `${purchase["numberOfSeats"]} ${seatsText} available until ${osparc.utils.Utils.formatDate(purchase["expiresAt"])}`,
          font: "text-14",
        });
        importSection.add(entry);
      });

      const importButton = new qx.ui.form.Button().set({
        label: this.tr("Import"),
        appearance: "strong-button",
        center: true,
        maxWidth: 200,
        alignX: "center",
      });
      this.bind("openBy", importButton, "visibility", {
        converter: openBy => openBy ? "visible" : "excluded"
      });
      importButton.addListener("execute", () => {
        this.fireDataEvent("modelImportRequested", {
          modelId: anatomicalModelsData["licensedResourceData"]["source"]["id"]
        });
      }, this);
      if (anatomicalModelsData["purchases"].length) {
        importSection.add(importButton);
      }
      return importSection;
    },
  }
});
